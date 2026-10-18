"""Exit probes use temporary files and synthetic processes, never live services."""
import json
import subprocess
import sys
import time
import weakref
from types import SimpleNamespace

import pytest

from app.backtest import worker
from app.backtest import worker_exit_diagnostics as probes


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_default_disabled_does_not_create_files(monkeypatch):
    monkeypatch.delenv(probes.ENV_NAME, raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("disabled probe must not create a directory")

    monkeypatch.setattr(probes.tempfile, "mkdtemp", forbidden)
    monkeypatch.setattr(probes, "ExitDiagnostics", forbidden)
    monkeypatch.setattr(probes.faulthandler, "dump_traceback_later", forbidden)
    monkeypatch.setattr(worker.threading, "Thread", forbidden)
    assert probes.parent_diagnostics() is None
    assert probes.child_diagnostics({probes.TASK_KEY: "unused"}) is None


def test_opt_in_requires_exact_value_and_internal_child_path(monkeypatch):
    monkeypatch.setenv(probes.ENV_NAME, "true")
    assert probes.parent_diagnostics() is None
    monkeypatch.setenv(probes.ENV_NAME, "1")
    assert probes.child_diagnostics({}) is None


def test_stage_clock_and_watchdog_resources_are_closed(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        probes.faulthandler, "dump_traceback_later",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        probes.faulthandler, "cancel_dump_traceback_later",
        lambda: calls.append("cancel"),
    )
    probe = probes.ExitDiagnostics(tmp_path, "child")
    probe.arm_stack_dump()
    probe.arm_stack_dump()
    probe.mark("duckdb_close_started")
    probe.mark("duckdb_close_completed")
    events, stacks = probe._events, probe._stacks
    probe.close(exit_imminent=True)
    probe.close()
    assert events.closed and stacks.closed
    assert len(calls) == 2
    assert calls[0][0] == (8.0,)
    assert calls[0][1]["repeat"] is False
    assert calls[0][1]["exit"] is False
    assert calls[1] == "cancel"
    stages = records(tmp_path / "child.jsonl")
    assert stages[-2]["stage"] == "duckdb_close_completed"
    assert stages[-1]["stage"] == "process_exit_imminent"
    assert all(row["elapsed_ms"] >= 0 for row in stages)
    assert all(row["since_previous_ms"] >= 0 for row in stages)
    assert [row["monotonic"] for row in stages] == sorted(
        row["monotonic"] for row in stages
    )


def test_unwritable_log_and_unavailable_stack_are_best_effort(monkeypatch, tmp_path):
    def unavailable(*args, **kwargs):
        raise RuntimeError("not recorded in logs")

    monkeypatch.setattr(probes.faulthandler, "dump_traceback_later", unavailable)
    probe = probes.ExitDiagnostics(tmp_path, "child")
    probe.arm_stack_dump()
    assert probe._stacks is None
    assert records(tmp_path / "child.jsonl")[-1]["stage"] == "stack_dump_unavailable"
    assert "not recorded" not in (tmp_path / "child.jsonl").read_text()
    probe.close()
    missing = probes.ExitDiagnostics(tmp_path / "missing", "child")
    missing.mark("cleanup_started")
    missing.arm_stack_dump()
    assert missing._stacks is None and not missing._armed
    missing.close()


def test_parent_timeout_retains_last_stage_and_original_deadlines(monkeypatch, tmp_path):
    monkeypatch.setenv(probes.ENV_NAME, "1")
    monkeypatch.setattr(probes.tempfile, "mkdtemp", lambda **kwargs: str(tmp_path))
    (tmp_path / "child.jsonl").write_text('{"stage":"feeder_join_started"}\n')
    messages = [{"type": "result", "payload": {"status": "ok"}}]
    joins = []
    process = SimpleNamespace(alive=True, exitcode=None)

    def terminate():
        process.alive = False
        process.exitcode = -15

    process.start = lambda: None
    process.is_alive = lambda: process.alive
    process.join = lambda timeout: joins.append(timeout)
    process.terminate = terminate
    queue = SimpleNamespace(
        get=lambda timeout: messages.pop(0), close=lambda: None, join_thread=lambda: None,
    )
    monkeypatch.setattr(worker.mp, "get_context", lambda _: SimpleNamespace(
        Queue=lambda: queue, Event=lambda: SimpleNamespace(set=lambda: None),
        Process=lambda **kwargs: process,
    ))
    task = {"kind": "mining", "config": {"private": "must-not-log"}}
    result = worker.run_worker_task(task)
    assert probes.TASK_KEY not in task
    assert joins == [10.0, 5.0]
    assert result["worker"]["worker_exitcode"] == -15
    assert result["worker"]["worker_exit_forcibly"] is True
    rows = records(tmp_path / "parent.jsonl")
    timeout = next(row for row in rows if row["stage"] == "exit_wait_timeout")
    assert timeout["child_stage"] == "feeder_join_started"
    assert timeout["is_alive"] is True and timeout["exitcode"] is None
    assert timeout["waited_ms"] >= 0
    assert "must-not-log" not in (tmp_path / "parent.jsonl").read_text()
    assert next(row for row in rows if row["stage"] == "termination_finished")["exitcode"] == -15


def test_missing_or_partial_child_stage_stays_unknown(tmp_path):
    probe = probes.ExitDiagnostics(tmp_path, "parent")
    assert probe.child_stage() is None
    (tmp_path / "child.jsonl").write_text('{"stage":')
    assert probe.child_stage() is None
    probe.close()


def test_probe_does_not_consume_lifecycle_test_clock(monkeypatch, tmp_path):
    def forbidden():
        raise AssertionError("diagnostics must not consume the lifecycle clock")

    monkeypatch.setattr(worker.time, "monotonic", forbidden)
    probe = probes.ExitDiagnostics(tmp_path, "parent")
    probe.mark("exit_wait_started")
    probe.close()
    assert records(tmp_path / "parent.jsonl")[0]["elapsed_ms"] >= 0


def test_real_bounded_stack_dump_in_isolated_child(tmp_path):
    # Controlled diagnostic test, not a reproduction of the mining exit timeout.
    script = """
import sys, time
from pathlib import Path
from app.backtest.worker_exit_diagnostics import ExitDiagnostics
probe = ExitDiagnostics(Path(sys.argv[1]), 'child')
probe.arm_stack_dump()
probe.mark('controlled_sleep_started')
deadline = time.monotonic() + 20
while True:
    stack = (Path(sys.argv[1]) / 'child-stacks.log').read_text()
    if 'Timeout (0:00:08)!' in stack and '<string>' in stack:
        break
    assert time.monotonic() < deadline, 'stack_dump_not_observed'
    time.sleep(0.05)
probe.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    stack = (tmp_path / "child-stacks.log").read_text()
    assert stack.count("Timeout (0:00:08)!") == 1
    assert '<string>' in stack


@pytest.mark.parametrize("stage", ["context", "queue", "event", "process", "rss", "start"])
def test_setup_failures_release_owned_resources(monkeypatch, tmp_path, stage):
    monkeypatch.setenv(probes.ENV_NAME, "1")
    monkeypatch.setattr(probes.tempfile, "mkdtemp", lambda **kwargs: str(tmp_path))
    calls = []
    def fail():
        raise RuntimeError("INJECTED_PRIVATE_FAILURE")
    def construct(name, value):
        if stage == name:
            fail()
        return value
    pipes = [SimpleNamespace(close=lambda: calls.append("pipe")) for _ in range(2)]
    queue = SimpleNamespace(close=lambda: calls.append("queue"),
                            join_thread=lambda: calls.append("feeder"), _reader=pipes[0], _writer=pipes[1])
    process = SimpleNamespace(pid=None, exitcode=None, close=lambda: calls.append("process"),
                              start=fail if stage == "start" else lambda: None)
    context = SimpleNamespace(Queue=lambda: construct("queue", queue),
                              Event=lambda: construct("event", object()),
                              Process=lambda **kwargs: construct("process", process))
    monkeypatch.setattr(worker.mp, "get_context", lambda _: construct("context", context))
    monkeypatch.setattr(worker, "_rss_bytes", fail if stage == "rss" else lambda: 1)
    with pytest.raises(RuntimeError, match="INJECTED_PRIVATE_FAILURE"):
        worker.run_worker_task({"kind": "mining"})
    assert ("queue" in calls) == (stage in {"event", "process", "rss", "start"})
    if "queue" in calls:
        assert calls.count("pipe") == 2 and "feeder" in calls
    assert ("process" in calls) == (stage in {"rss", "start"})
    rows = records(tmp_path / "parent.jsonl")
    assert rows[-1]["stage"] == "parent_cleanup_finished"
    assert any(row["stage"] == "setup_failed" for row in rows)
    assert "INJECTED_PRIVATE_FAILURE" not in (tmp_path / "parent.jsonl").read_text()
    # Reopen exclusively: the diagnostic stream was closed on failure.
    (tmp_path / "parent.jsonl").rename(tmp_path / "closed.jsonl")


def test_terminate_precedes_any_post_deadline_diagnostic_io(monkeypatch, tmp_path):
    calls = []
    process = SimpleNamespace(alive=True, exitcode=None, pid=None)
    expired = False
    def join(timeout):
        nonlocal expired
        calls.append(("join", timeout))
        if timeout == 10:
            expired = True
    def terminate():
        calls.append("terminate")
        process.alive, process.exitcode = False, -15
    process.start = lambda: None
    process.join, process.terminate = join, terminate
    process.is_alive = lambda: process.alive
    def io(*args, **kwargs):
        assert not (expired and process.alive), "diagnostic_io_delayed_termination"
        calls.append("io")
        time.sleep(0.01)  # Simulated slow diagnostic I/O, after terminate only.
    probe = SimpleNamespace(directory=tmp_path, now=time.monotonic, mark=io, close=io,
                            child_stage=lambda: (io(), "feeder_join_started")[1])
    monkeypatch.setattr(worker, "parent_diagnostics", lambda: probe)
    queue = SimpleNamespace(get=lambda **kwargs: {"type": "result", "payload": {}},
                            close=lambda: None, join_thread=lambda: None)
    monkeypatch.setattr(worker.mp, "get_context", lambda _: SimpleNamespace(
        Queue=lambda: queue, Event=object, Process=lambda **kwargs: process))
    worker.run_worker_task({"kind": "mining"})
    assert calls[:3] == [("join", 10.0), "terminate", ("join", 5.0)]


def test_queue_cleanup_exceptions_do_not_skip_pipes_or_probe(monkeypatch, tmp_path):
    monkeypatch.setenv(probes.ENV_NAME, "1")
    monkeypatch.setattr(probes.tempfile, "mkdtemp", lambda **kwargs: str(tmp_path))
    calls = []
    def bad():
        raise OSError("PRIVATE_CLEANUP_BODY")
    queue = SimpleNamespace(close=bad, join_thread=bad,
                            _reader=SimpleNamespace(close=lambda: calls.append("reader")),
                            _writer=SimpleNamespace(close=lambda: calls.append("writer")))
    def fail_event():
        raise RuntimeError("original_setup_failure")
    monkeypatch.setattr(worker.mp, "get_context", lambda _: SimpleNamespace(Queue=lambda: queue, Event=fail_event))
    with pytest.raises(RuntimeError, match="original_setup_failure"):
        worker.run_worker_task({"kind": "mining"})
    assert calls == ["reader", "writer"]
    rows = records(tmp_path / "parent.jsonl")
    assert {r.get("reason") for r in rows} >= {"queue_close_failed", "feeder_join_failed"}
    assert rows[-1]["stage"] == "parent_cleanup_incomplete"
    assert "PRIVATE_CLEANUP_BODY" not in (tmp_path / "parent.jsonl").read_text()


def test_unknown_fields_and_child_stages_are_not_evidence(tmp_path):
    probe = probes.ExitDiagnostics(tmp_path, "parent")
    probe.mark("cleanup_started", reason="PRIVATE", text="PRIVATE", is_alive="PRIVATE")
    probe.mark("PRIVATE")
    (tmp_path / "child.jsonl").write_text('{"stage":"PRIVATE"}')
    assert probe.child_stage() is None
    probe.close()
    assert "PRIVATE" not in (tmp_path / "parent.jsonl").read_text()


def test_real_prestart_queue_handles_and_event_references_are_released(monkeypatch):
    monkeypatch.delenv(probes.ENV_NAME, raising=False)
    context = worker.mp.get_context("spawn")
    saved = {}
    def queue_factory():
        queue = context.Queue()
        saved["reader"], saved["writer"] = queue._reader, queue._writer
        return queue
    def event_factory():
        event = context.Event()
        saved["event"] = weakref.ref(event)
        return event
    def process_factory(**kwargs):
        process = context.Process(**kwargs)
        saved["process"] = process
        return process
    def fail_start(self):
        raise RuntimeError("start_failure_with_traceback")
    monkeypatch.setattr(worker.mp.process.BaseProcess, "start", fail_start)
    monkeypatch.setattr(worker.mp, "get_context", lambda _: SimpleNamespace(
        Queue=queue_factory, Event=event_factory, Process=process_factory))
    with pytest.raises(RuntimeError, match="start_failure_with_traceback") as caught:
        worker.run_worker_task({"kind": "mining"})
    assert caught.value.__traceback__ is not None  # Retaining the failure must not retain Event/pipe ownership.
    assert saved["reader"].closed and saved["writer"].closed
    assert saved["process"]._closed and not saved["process"]._args
    assert saved["event"]() is None


@pytest.mark.parametrize("failure", ["close", "join_thread"])
def test_child_cleanup_failure_has_fixed_code_and_cancels_watchdog(monkeypatch, tmp_path, failure):
    monkeypatch.setenv(probes.ENV_NAME, "1")
    watchdog = []
    monkeypatch.setattr(probes.faulthandler, "dump_traceback_later", lambda *args, **kwargs: watchdog.append("arm"))
    monkeypatch.setattr(probes.faulthandler, "cancel_dump_traceback_later", lambda: watchdog.append("cancel"))
    def sampler_failure():
        raise RuntimeError("PRIVATE_SAMPLER_FAILURE")
    monkeypatch.setattr(worker, "_PeakRssSampler", sampler_failure)
    monkeypatch.setattr(worker, "_error_message", lambda _: "fixture_error")
    def bad():
        raise OSError("PRIVATE_CLEANUP_BODY")
    queue = SimpleNamespace(put=lambda _: None,
                            close=bad if failure == "close" else lambda: None,
                            join_thread=bad if failure == "join_thread" else lambda: None)
    class Exited(BaseException):
        pass
    def exit_now(code):
        assert code == 0  # Preserve original worker exit semantics, even on task error.
        raise Exited
    monkeypatch.setattr(worker.os, "_exit", exit_now)
    with pytest.raises(Exited):
        worker._worker_entry({probes.TASK_KEY: str(tmp_path)}, queue, None)
    rows = records(tmp_path / "child.jsonl")
    stages = [r["stage"] for r in rows]
    assert ("queue_close_failed" if failure == "close" else "feeder_join_failed") in stages
    assert "cleanup_incomplete" in stages and "cleanup_completed" not in stages
    assert stages[-1] == "process_exit_imminent" and watchdog == ["arm", "cancel"]
    assert "PRIVATE" not in (tmp_path / "child.jsonl").read_text()


@pytest.mark.parametrize("failure", ["write", "flush"])
def test_probe_write_flush_failure_is_best_effort_and_closes(tmp_path, failure):
    probe = probes.ExitDiagnostics(tmp_path, "parent")
    probe._events.close()
    closed = []
    def bad(*args):
        raise OSError("PRIVATE_IO_FAILURE")
    probe._events = SimpleNamespace(write=bad if failure == "write" else lambda *args: None,
                                    flush=bad, close=lambda: closed.append(True))
    probe.mark("cleanup_started")
    probe.close()
    assert closed == [True] and probe._events is None


def test_normal_probe_exit_leaves_empty_stack_and_no_rearm(monkeypatch, tmp_path):
    probe = probes.ExitDiagnostics(tmp_path, "child")
    probe.arm_stack_dump()
    probe.close(exit_imminent=True)
    probe.close()
    probe.arm_stack_dump()
    assert (tmp_path / "child-stacks.log").read_text() == ""
    assert probe._stacks is None and probe._events is None and not probe._armed


def test_parent_probe_directory_failure_does_not_prevent_result(monkeypatch):
    monkeypatch.setenv(probes.ENV_NAME, "1")
    def bad(**kwargs):
        raise OSError("PRIVATE_PROBE_FAILURE")
    monkeypatch.setattr(probes.tempfile, "mkdtemp", bad)
    queue = SimpleNamespace(get=lambda **kwargs: {"type": "result", "payload": {}},
                            close=lambda: None, join_thread=lambda: None)
    process = SimpleNamespace(start=lambda: None, join=lambda **kwargs: None,
                              is_alive=lambda: False, exitcode=0)
    monkeypatch.setattr(worker.mp, "get_context", lambda _: SimpleNamespace(
        Queue=lambda: queue, Event=object, Process=lambda **kwargs: process))
    result = worker.run_worker_task({"kind": "mining"})
    assert result["worker"]["worker_exitcode"] == 0


@pytest.mark.parametrize("enabled", [False, True])
def test_parent_queue_cleanup_failure_still_raises_after_success(monkeypatch, tmp_path, enabled):
    monkeypatch.setenv(probes.ENV_NAME, "1" if enabled else "")
    monkeypatch.setattr(probes.tempfile, "mkdtemp", lambda **kwargs: str(tmp_path))
    closed = []
    def bad():
        raise OSError("fixture_queue_close_failure")
    queue = SimpleNamespace(get=lambda **kwargs: {"type": "result", "payload": {}},
                            close=bad, join_thread=lambda: closed.append("join"))
    process = SimpleNamespace(start=lambda: None, join=lambda **kwargs: None,
                              is_alive=lambda: False, exitcode=0)
    monkeypatch.setattr(worker.mp, "get_context", lambda _: SimpleNamespace(
        Queue=lambda: queue, Event=object, Process=lambda **kwargs: process))
    with pytest.raises(OSError, match="fixture_queue_close_failure"):
        worker.run_worker_task({"kind": "mining"})
    assert closed == ["join"]
    if enabled:
        assert records(tmp_path / "parent.jsonl")[-1]["stage"] == "parent_cleanup_incomplete"
