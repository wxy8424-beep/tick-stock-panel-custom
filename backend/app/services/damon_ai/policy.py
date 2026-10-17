"""In-process execution policy; production has no registered handlers or HTTP executor."""
import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from time import monotonic
from types import MappingProxyType
from typing import Literal
from uuid import uuid4

from pydantic import Field

from .contracts import Contract, DataMode, Market, ResearchContext, ToolOutput, ToolResult


class ToolBudget(Contract):
    max_calls: int = Field(default=4, ge=1, le=8)
    timeout_seconds: float = Field(default=5, gt=0, le=30)
    turn_timeout_seconds: float = Field(default=30, gt=0, le=120)
    cleanup_timeout_seconds: float = Field(default=0.1, gt=0, le=1)
    max_concurrent_calls: int = Field(default=1, ge=1, le=4)
    max_output_chars: int = Field(default=4000, ge=64, le=8000)


@dataclass(frozen=True)
class ReadTool:
    handler: Callable[[ResearchContext], Awaitable[ToolOutput]]
    market: Market
    data_mode: DataMode
    effect: Literal["read", "write"] = "read"


class ReadOnlyTurn:
    """One instance per server-owned turn; callers cannot grant permissions.

    Handlers are trusted application code, not a sandbox. Future registrations require
    side-effect review. Do not register sync handlers, providers or generic dispatchers.
    Deadlines require a yielding event loop. Python cannot forcibly kill a coroutine;
    an uncooperative handler stays tracked and this instance remains closed forever.
    The response deadline is execution deadline plus the bounded cleanup allowance.
    """

    def __init__(self, context: ResearchContext, *, tools: Mapping[str, ReadTool] | None = None,
                 budget: ToolBudget | None = None):
        self.context = context
        self.tools = MappingProxyType(dict(tools or {}))
        self.budget = budget or ToolBudget()
        self.cancelled = asyncio.Event()
        self.calls = 0
        self._deadline = monotonic() + self.budget.turn_timeout_seconds
        self._closed_reason: str | None = None
        self._active: set[asyncio.Task] = set()

    @property
    def pending_tasks(self) -> int:
        return sum(not task.done() for task in self._active)

    def _halt(self, reason: str) -> None:
        if self._closed_reason is None:
            self._closed_reason = reason
        self.cancelled.set()

    def _finished(self, task: asyncio.Task) -> None:
        self._active.discard(task)
        if not task.cancelled():
            task.exception()  # Consume failures without exposing upstream text.

    def cancel(self) -> None:
        self._halt("cancelled")

    async def execute(self, name: str, context: ResearchContext) -> ToolResult:
        request_id = uuid4().hex

        def result(code, output=None, cleanup_state="not_needed"):
            status = "completed" if code == "ok" else "cancelled" if code == "cancelled" else "blocked"
            return ToolResult(request_id=request_id, status=status, code=code, output=output,
                              cleanup_state=cleanup_state)

        if self.cancelled.is_set():
            return result("cancelled" if self._closed_reason == "cancelled" else "turn_closed")
        if monotonic() >= self._deadline:
            self._halt("deadline")
            return result("deadline")
        tool = self.tools.get(name)
        if tool is None:
            return result("unregistered")
        if tool.effect != "read":
            return result("write_denied")
        if context != self.context or (tool.market, tool.data_mode) != (context.market, context.data_mode):
            return result("context_conflict")
        if self.calls >= self.budget.max_calls:
            return result("budget")
        if self.pending_tasks >= self.budget.max_concurrent_calls:
            return result("concurrency_limit")
        # Reserve before awaiting: concurrent calls share the same turn budget.
        self.calls += 1
        async def invoke():
            return await tool.handler(self.context)

        work = asyncio.create_task(invoke())
        self._active.add(work)
        work.add_done_callback(self._finished)
        cancellation = asyncio.create_task(self.cancelled.wait())
        tool_deadline = monotonic() + self.budget.timeout_seconds
        expires = min(tool_deadline, self._deadline)
        code, output = "tool_error", None
        try:
            done, _ = await asyncio.wait(
                {work, cancellation}, timeout=max(0, expires - monotonic()),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if self.cancelled.is_set():
                code = "cancelled" if self._closed_reason == "cancelled" else "turn_closed"
            elif monotonic() >= expires or work not in done:
                code = "deadline" if self._deadline <= tool_deadline else "timeout"
            elif work.cancelled():
                code = "cancelled"
            else:
                output = ToolOutput.model_validate(work.result())
                code = "ok"
                if any(item.context != self.context for item in output.evidence):
                    code = "context_conflict"
                elif len(output.model_dump_json()) > self.budget.max_output_chars:
                    code = "output_limit"
            if code != "ok":
                self._halt(code)
        except asyncio.CancelledError:
            self.cancel()
            raise
        except Exception:  # noqa: BLE001 - fixed error only; no raw upstream text or logging
            code = "tool_error"
            self._halt(code)
        finally:
            if not work.done():
                work.cancel()
            cancellation.cancel()
            # wait_for/gather can wait forever when a handler suppresses cancellation.
            # Keep unfinished work tracked, close this turn, and report its real state.
            try:
                await asyncio.wait({work, cancellation}, timeout=self.budget.cleanup_timeout_seconds)
            except asyncio.CancelledError:
                # Cancellation can arrive during cleanup after a successful handler.
                self.cancel()
                raise
        if code == "ok" and self.cancelled.is_set():
            code = "cancelled" if self._closed_reason == "cancelled" else "turn_closed"
        return result(code, output if code == "ok" else None,
                      "finished" if work.done() else "still_running")
