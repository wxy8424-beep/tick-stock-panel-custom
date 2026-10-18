"""Opt-in, best-effort exit probes; never serialize task or result payloads."""
from __future__ import annotations

import faulthandler
import json
import math
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from time import monotonic

ENV_NAME = "TSP_WORKER_EXIT_DIAGNOSTICS"
TASK_KEY = "_exit_diagnostics_dir"
STAGES = frozenset({
    "stack_dump_armed", "stack_dump_unavailable", "terminal_put_started", "terminal_enqueued",
    "cleanup_started", "duckdb_close_started", "duckdb_close_completed", "duckdb_close_failed",
    "queue_close_started", "queue_close_completed", "queue_close_failed", "feeder_join_started",
    "feeder_join_completed", "feeder_join_failed", "cleanup_completed", "cleanup_incomplete",
    "diagnostic_cleanup_started", "process_exit_imminent", "terminal_received", "terminal_missing",
    "exit_wait_returned", "exit_wait_timeout", "termination_finished", "setup_failed",
    "parent_cleanup_failed", "parent_cleanup_finished", "parent_cleanup_incomplete",
    "controlled_sleep_started", "exit_wait_started",
})
REASONS = frozenset({
    "context_create", "queue_create", "event_create", "process_create", "rss_prepare", "process_start",
    "queue_close_failed", "feeder_join_failed", "queue_pipe_close_failed", "process_close_failed",
    "process_cleanup_failed",
})


class ExitDiagnostics:
    def __init__(self, directory: Path, role: str) -> None:
        if role not in {"parent", "child"}:
            raise ValueError("invalid_diagnostic_role")
        self.directory = directory
        self.role = role
        self._started = self._previous = monotonic()
        self._events = None
        self._stacks = None
        self._armed = False
        self._dump_attempted = False
        self._closed = False
        with suppress(OSError):
            self._events = (directory / f"{role}.jsonl").open("x", encoding="utf-8")

    @staticmethod
    def now() -> float:
        # Captured reference, independent of worker lifecycle-clock mocks.
        return monotonic()

    def mark(self, stage: str, **fields) -> None:
        if self._events is None or stage not in STAGES:
            return
        safe = {}
        for name, value in fields.items():
            if ((name == "reason" and isinstance(value, str) and value in REASONS)
                    or (name == "terminal_type" and isinstance(value, str) and value in {"result", "error"})
                    or (name == "child_stage" and (value is None or (isinstance(value, str) and value in STAGES)))
                    or (name == "is_alive" and isinstance(value, bool))
                    or (name == "exitcode" and (value is None or type(value) is int))
                    or (name in {"waited_ms", "delay_seconds", "wait_started_monotonic"}
                        and type(value) in {int, float} and math.isfinite(value))):
                safe[name] = value
        now = monotonic()
        record = {
            "stage": stage, "pid": os.getpid(), "monotonic": now,
            "elapsed_ms": (now - self._started) * 1000,
            "since_previous_ms": (now - self._previous) * 1000,
            **safe,
        }
        self._previous = now
        with suppress(OSError, ValueError):
            self._events.write(json.dumps(record) + "\n")
            self._events.flush()

    def arm_stack_dump(self) -> None:
        """One dump before the parent's 10s deadline; no repeating watchdog."""
        if self._dump_attempted or self._closed:
            return
        self._dump_attempted = True
        try:
            self._stacks = (self.directory / "child-stacks.log").open("x")
            faulthandler.dump_traceback_later(
                8.0, repeat=False, file=self._stacks, exit=False,
            )
            self._armed = True
            self.mark("stack_dump_armed", delay_seconds=8.0)
        except (OSError, RuntimeError, ValueError):
            self.mark("stack_dump_unavailable")
            if self._stacks is not None:
                with suppress(OSError):
                    self._stacks.close()
                self._stacks = None

    def child_stage(self) -> str | None:
        # Bounded tail read; a partial/unreadable record means UNKNOWN, not failure.
        try:
            with (self.directory / "child.jsonl").open("rb") as stream:
                stream.seek(0, 2)
                stream.seek(max(0, stream.tell() - 65536))
                lines = stream.read(65536).splitlines()
            stage = json.loads(lines[-1])["stage"] if lines else None
            return stage if isinstance(stage, str) and stage in STAGES else None
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            return None

    def close(self, *, exit_imminent: bool = False) -> None:
        if self._closed:
            return
        self._closed = True
        if self._armed:
            with suppress(OSError, RuntimeError):
                faulthandler.cancel_dump_traceback_later()
            self._armed = False
        if self._stacks is not None:
            with suppress(OSError):
                self._stacks.close()
        if exit_imminent:
            self.mark("process_exit_imminent")
        if self._events is not None:
            with suppress(OSError):
                self._events.close()
        self._stacks = self._events = None


def parent_diagnostics() -> ExitDiagnostics | None:
    if os.environ.get(ENV_NAME) != "1":
        return None
    try:
        directory = Path(tempfile.mkdtemp(prefix="tsp-worker-exit-"))
        return ExitDiagnostics(directory, "parent")
    except OSError:
        return None


def child_diagnostics(task: dict) -> ExitDiagnostics | None:
    if os.environ.get(ENV_NAME) != "1" or TASK_KEY not in task:
        return None
    return ExitDiagnostics(Path(task[TASK_KEY]), "child")
