"""Bounded, process-local text turns. No dispatcher, business tools or persistence."""
import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from time import monotonic
from uuid import uuid4

from httpx import TimeoutException
from openai import APITimeoutError
from pydantic import BaseModel, ConfigDict, Field

from app.services import ai_provider

from .contracts import TEXT_MAX_CODE_POINTS
from .profiles import ChatError, Snapshot


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=TEXT_MAX_CODE_POINTS)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str = Field(pattern=r"^[a-zA-Z0-9._-]{1,64}$")
    conversation_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    messages: list[Message] = Field(min_length=1, max_length=24)


@dataclass
class Conversation:
    actor: str
    calls: int = 0
    touched: float = field(default_factory=monotonic)
    active: object = None


@dataclass
class Turn:
    conversation_id: str
    owner: Conversation
    snapshot: Snapshot = field(repr=False)
    turn_id: str = field(default_factory=lambda: uuid4().hex)
    request_id: str = field(default_factory=lambda: uuid4().hex)
    cancelled: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None
    sequence: int = 0
    code: str = "completed"

    def event(self, kind, **payload):
        self.sequence += 1
        return {"type": kind, "conversation_id": self.conversation_id, "turn_id": self.turn_id,
                "request_id": self.request_id, "sequence": self.sequence, **payload}


class ChatRegistry:
    """Single worker only. Active tasks keep admission until actual exit, including cleanup."""
    def __init__(self, timeout=60.0, cleanup=0.2):
        self.conversations: OrderedDict[str, Conversation] = OrderedDict()
        self.active: dict[str, Turn] = {}
        self.admissions: dict[str, tuple[float, int]] = {}
        self.timeout, self.cleanup = timeout, cleanup

    def admit(self, actor, req, snapshot):
        self.admissions = {key: entry for key, entry in self.admissions.items()
                           if monotonic() - entry[0] < 3600}
        epoch, count = self.admissions.get(actor, (monotonic(), 0))
        if count >= 60 or (actor not in self.admissions and len(self.admissions) >= 256):
            raise ChatError("budget")
        for cid, conversation in list(self.conversations.items()):
            if conversation.active is None and monotonic() - conversation.touched > 1800:
                del self.conversations[cid]
        # Reject busy requests before allocating a new conversation slot.
        if len(self.active) >= 8 or sum(t.owner.actor == actor for t in self.active.values()) >= 2:
            raise ChatError("busy")
        cid = req.conversation_id
        if cid is None:
            if len(self.conversations) >= 256:
                raise ChatError("capacity")
            cid = uuid4().hex
            self.conversations[cid] = Conversation(actor)
        owner = self.conversations.get(cid)
        if owner is None or owner.actor != actor:
            raise ChatError("conversation_unavailable")
        if owner.active:
            raise ChatError("busy")
        if owner.calls >= 20:
            raise ChatError("budget")
        owner.calls += 1
        self.admissions[actor] = (epoch, count + 1)
        owner.touched = monotonic()
        turn = Turn(cid, owner, snapshot)
        owner.active = turn
        self.active[turn.turn_id] = turn
        return turn

    def release(self, turn):
        self.active.pop(turn.turn_id, None)
        turn.owner.active = None
        turn.owner.touched = monotonic()

    def cancel(self, actor, conversation_id, turn_id):
        turn = self.active.get(turn_id)
        if turn is None or turn.owner.actor != actor or turn.conversation_id != conversation_id:
            raise ChatError("turn_unavailable")
        turn.cancelled.set()
        if turn.task and not turn.task.done() and not turn.task.cancelling():
            turn.task.cancel()
        return turn

    async def stop(self, turn):
        turn.cancelled.set()
        task = turn.task
        if task and not task.done():
            if turn.code == "completed":
                turn.code = "cancelled"
            if not task.cancelling():
                task.cancel()
            await asyncio.wait({task}, timeout=self.cleanup)
        return "finished" if task is None or task.done() else "still_running"

    async def stream(self, turn, req, disconnected):
        queue = asyncio.Queue(maxsize=8)
        snapshot = turn.snapshot

        async def produce():
            source = ai_provider.stream_snapshot_text(
                [{"role": "system", "content": "You are Damon, a text-only assistant. No tools or market evidence are available. Never claim to have executed actions or verified market data."},
                 *[m.model_dump() for m in req.messages]],
                api_key=snapshot.api_key, base_url=snapshot.base_url, model=snapshot.profile.model,
                protocol=snapshot.profile.protocol, user_agent=snapshot.user_agent,
                max_tokens=snapshot.max_tokens, timeout=self.timeout)
            total, emitted, buffer = 0, 0, ""
            sensitive = (snapshot.api_key, snapshot.base_url)
            hold = max(map(len, sensitive))

            async def emit(text):
                nonlocal emitted
                emitted += len(text)
                # Redaction can expand short test/configured secrets. Bound the
                # delivered body too, before enqueueing any oversized fragment.
                if emitted > TEXT_MAX_CODE_POINTS:
                    raise ChatError("output_limit")
                await queue.put(text)

            try:
                async for delta in source:
                    if turn.cancelled.is_set():
                        return
                    total += len(delta)
                    if total > TEXT_MAX_CODE_POINTS:
                        raise ChatError("output_limit")
                    buffer += delta
                    for secret in sensitive:
                        buffer = buffer.replace(secret, "[redacted]")
                    if len(buffer) > hold:
                        await emit(buffer[:-hold])
                        buffer = buffer[-hold:]
                if buffer and not turn.cancelled.is_set():
                    await emit(buffer)
            except asyncio.CancelledError:
                if turn.code != "timeout":
                    turn.code = "cancelled"
                raise
            except ChatError as exc:
                if turn.code == "completed":
                    turn.code = exc.code
            except (TimeoutError, TimeoutException, APITimeoutError):
                if turn.code == "completed":
                    turn.code = "timeout"
            except Exception:  # noqa: BLE001 - fixed classification, no raw text/logging
                if turn.code == "completed":
                    turn.code = "upstream_error"
            finally:
                await source.aclose()

        turn.task = asyncio.create_task(produce())

        async def expire():
            await asyncio.sleep(self.timeout)
            turn.code = "timeout"
            await self.stop(turn)

        watchdog = asyncio.create_task(expire())

        def finished(task):
            watchdog.cancel()
            if not task.cancelled():
                error = task.exception()
                if error is not None and turn.code == "completed":
                    turn.code = "upstream_error"
            self.release(turn)

        turn.task.add_done_callback(finished)
        deadline = monotonic() + self.timeout
        last_ping = monotonic()
        try:
            yield turn.event("start", profile_id=snapshot.profile.profile_id)
            while True:
                if turn.cancelled.is_set() or await disconnected():
                    cleanup = await self.stop(turn)
                    yield turn.event("error" if turn.code == "timeout" else "cancelled",
                                     code=turn.code, cleanup_state=cleanup)
                    return
                if monotonic() >= deadline:
                    turn.code = "timeout"
                    cleanup = await self.stop(turn)
                    yield turn.event("error", code="timeout", cleanup_state=cleanup)
                    return
                if turn.task.done() and queue.empty():
                    yield turn.event("done" if turn.code == "completed" else "error", code=turn.code)
                    return
                try:
                    delta = await asyncio.wait_for(queue.get(), timeout=0.1)
                except TimeoutError:
                    if monotonic() - last_ping >= 10:
                        last_ping = monotonic()
                        yield turn.event("ping")
                    continue
                if not turn.cancelled.is_set() and monotonic() < deadline:
                    yield turn.event("delta", text=delta)
        finally:
            await self.stop(turn)


registry = ChatRegistry()
