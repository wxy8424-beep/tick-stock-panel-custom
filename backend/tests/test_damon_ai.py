"""Offline policy tests: no application lifespan, models or production services."""
import asyncio
import socket
import sqlite3
import subprocess
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.damon_ai import router
from app.services.damon_ai.contracts import (
    EvidenceReference,
    ProfileReference,
    ResearchContext,
    ToolOutput,
)
from app.services.damon_ai.policy import ReadOnlyTurn, ReadTool, ToolBudget


def context(market="CN", mode="simulation"):
    return ResearchContext(market=market, data_mode=mode, as_of=datetime(2026, 10, 17, tzinfo=UTC))


@pytest.fixture(autouse=True)
def no_external_effects(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("external effects forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    # Windows asyncio uses a loopback socketpair internally; do not disable it.
    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)


async def output(_context):
    return ToolOutput(summary="offline")


async def test_empty_registry_rejects_every_action():
    turn = ReadOnlyTurn(context())
    for name in ("unknown", "run_backtest", "run_strategy", "sync_data", "shell", "sql",
                 "python", "http", "read_file", "trade", "create_signal_strategy"):
        assert (await turn.execute(name, context())).code == "unregistered"
    assert turn.calls == 0


async def test_write_and_context_checks_precede_handler_execution():
    calls = []

    async def handler(ctx):
        calls.append(ctx)
        return ToolOutput(summary="not called")

    turn = ReadOnlyTurn(context(), tools={
        "write": ReadTool(handler, "CN", "simulation", "write"),
        "read": ReadTool(handler, "CN", "simulation"),
    })
    assert (await turn.execute("write", context())).code == "write_denied"
    for ctx in (context("HK"), context(mode="preview"),
                context().model_copy(update={"as_of": datetime(2020, 1, 1, tzinfo=UTC)})):
        assert (await turn.execute("read", ctx)).code == "context_conflict"
    assert calls == []


async def test_budget_is_shared_across_concurrent_calls():
    turn = ReadOnlyTurn(context(), tools={"read": ReadTool(output, "CN", "simulation")},
                        budget=ToolBudget(max_calls=1))
    results = await asyncio.gather(turn.execute("read", context()), turn.execute("read", context()))
    assert sorted(item.code for item in results) == ["budget", "ok"]


async def test_turn_deadline_includes_idle_time_and_blocks_dispatch():
    turn = ReadOnlyTurn(context(), tools={"read": ReadTool(output, "CN", "simulation")},
                        budget=ToolBudget(turn_timeout_seconds=0.01))
    await asyncio.sleep(0.02)
    assert (await turn.execute("read", context())).code == "deadline"
    assert turn.calls == 0
    assert (await turn.execute("read", context())).code == "turn_closed"


@pytest.mark.parametrize("suppress", [False, True])
@pytest.mark.parametrize("trigger", ["timeout", "cancelled"])
async def test_bounded_cleanup_never_claims_forced_termination(suppress, trigger):
    release, started = asyncio.Event(), asyncio.Event()

    async def slow(_ctx):
        started.set()
        if suppress:
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    continue
            return ToolOutput(summary="late success must be ignored")
        try:
            await asyncio.Event().wait()
        finally:
            await release.wait()  # A cooperative handler can still have slow cleanup.

    turn = ReadOnlyTurn(context(), tools={"read": ReadTool(slow, "CN", "simulation")},
                        budget=ToolBudget(timeout_seconds=0.01 if trigger == "timeout" else 1,
                                          cleanup_timeout_seconds=0.01))
    call = asyncio.create_task(turn.execute("read", context()))
    await started.wait()
    if trigger == "cancelled":
        turn.cancel()
        turn.cancel()
    try:
        done, _ = await asyncio.wait({call}, timeout=0.5)
        assert call in done, "execution must not wait indefinitely for cleanup"
        result = call.result()
        assert result.code == trigger and result.output is None
        assert result.cleanup_state == "still_running"
        assert turn.pending_tasks == 1
        assert (await turn.execute("read", context())).code == (
            "turn_closed" if trigger == "timeout" else "cancelled")
        assert turn.calls == 1
    finally:
        release.set()  # Never leave a deliberately uncooperative test task behind.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        if not call.done():
            call.cancel()
        await asyncio.gather(call, return_exceptions=True)
    assert turn.pending_tasks == 0


async def test_cleanup_exception_remains_a_safe_timeout(caplog):
    async def broken_cleanup(_ctx):
        try:
            await asyncio.Event().wait()
        finally:
            raise RuntimeError("FAKE_CLEANUP_ERROR_FOR_TEST_ONLY")

    turn = ReadOnlyTurn(context(), tools={"read": ReadTool(broken_cleanup, "CN", "simulation")},
                        budget=ToolBudget(timeout_seconds=0.01))
    result = await turn.execute("read", context())
    assert result.code == "timeout" and result.output is None
    assert result.cleanup_state == "finished" and turn.pending_tasks == 0
    assert "FAKE_CLEANUP_ERROR_FOR_TEST_ONLY" not in result.model_dump_json() + caplog.text
    assert (await turn.execute("read", context())).code == "turn_closed"


async def test_errors_and_timeouts_close_turn_without_refunding_budget():
    async def broken(_ctx):
        raise RuntimeError("FAKE_PRIVATE_PATH_FOR_TEST_ONLY")

    turn = ReadOnlyTurn(context(), tools={"read": ReadTool(broken, "CN", "simulation")})
    assert (await turn.execute("read", context())).code == "tool_error"
    assert (await turn.execute("read", context())).code == "turn_closed"
    assert turn.calls == 1


async def test_turn_deadline_stops_inflight_handler_and_concurrent_admission_is_bounded():
    started = asyncio.Event()

    async def slow(_ctx):
        started.set()
        await asyncio.Event().wait()

    turn = ReadOnlyTurn(context(), tools={"read": ReadTool(slow, "CN", "simulation")},
                        budget=ToolBudget(turn_timeout_seconds=0.05, timeout_seconds=1))
    call = asyncio.create_task(turn.execute("read", context()))
    await started.wait()
    assert (await turn.execute("read", context())).code == "concurrency_limit"
    assert (await call).code == "deadline"
    assert turn.pending_tasks == 0


async def test_timeout_and_cancellation_release_handlers():
    released = asyncio.Event()

    async def slow(_ctx):
        try:
            await asyncio.Event().wait()
        finally:
            released.set()

    tools = {"read": ReadTool(slow, "CN", "simulation")}
    turn = ReadOnlyTurn(context(), tools=tools, budget=ToolBudget(timeout_seconds=0.01))
    assert (await turn.execute("read", context())).code == "timeout"
    assert released.is_set()
    released.clear()
    turn = ReadOnlyTurn(context(), tools=tools)
    task = asyncio.create_task(turn.execute("read", context()))
    await asyncio.sleep(0)
    turn.cancel()
    turn.cancel()
    assert (await task).code == "cancelled"
    assert released.is_set()
    assert (await turn.execute("read", context())).code == "cancelled"


async def test_outer_cancellation_cancels_the_turn():
    started, released = asyncio.Event(), asyncio.Event()

    async def slow(_ctx):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            released.set()

    turn = ReadOnlyTurn(context(), tools={"read": ReadTool(slow, "CN", "simulation")})
    task = asyncio.create_task(turn.execute("read", context()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert released.is_set()
    assert (await turn.execute("read", context())).code == "cancelled"


async def test_outer_cancellation_during_cleanup_also_closes_turn(monkeypatch):
    cleanup_started = asyncio.Event()
    original_wait = asyncio.wait
    waits = 0

    async def delayed_cleanup(*args, **kwargs):
        nonlocal waits
        waits += 1
        if waits == 2:
            cleanup_started.set()
            await asyncio.Event().wait()
        return await original_wait(*args, **kwargs)

    monkeypatch.setattr(asyncio, "wait", delayed_cleanup)
    turn = ReadOnlyTurn(context(), tools={"read": ReadTool(output, "CN", "simulation")})
    task = asyncio.create_task(turn.execute("read", context()))
    await cleanup_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await turn.execute("read", context())).code == "cancelled"
    assert turn.calls == 1 and turn.pending_tasks == 0


async def test_output_limit_evidence_context_and_safe_errors(caplog):
    async def long(_ctx):
        return ToolOutput(summary="x" * 100)

    turn = ReadOnlyTurn(context(), tools={"read": ReadTool(long, "CN", "simulation")},
                        budget=ToolBudget(max_output_chars=64))
    assert (await turn.execute("read", context())).code == "output_limit"

    async def conflict(_ctx):
        return ToolOutput(summary="conflict", evidence=(EvidenceReference(
            evidence_id="demo", context=context("US"), source="simulated_event", summary="demo"),))

    turn = ReadOnlyTurn(context(), tools={"read": ReadTool(conflict, "CN", "simulation")})
    assert (await turn.execute("read", context())).code == "context_conflict"
    sentinel = "FAKE_SECRET_FOR_LEAK_TEST_ONLY"

    async def broken(_ctx):
        raise RuntimeError(sentinel)

    turn = ReadOnlyTurn(context(), tools={"read": ReadTool(broken, "CN", "simulation")})
    result = await turn.execute("read", context())
    assert result.code == "tool_error"
    assert sentinel not in result.model_dump_json() + caplog.text
    assert len(result.request_id) == 32


@pytest.mark.parametrize("mode,source", [("preview", "synthetic_fixture"), ("simulation", "simulated_event")])
def test_nonproduction_evidence_cannot_be_promoted(mode, source):
    with pytest.raises(ValidationError):
        EvidenceReference(evidence_id="demo", context=context(mode=mode), source=source,
                          is_production=True, summary="demo")
    with pytest.raises(ValidationError):
        EvidenceReference(evidence_id="demo", context=context(), source="archive", summary="demo")


def test_profile_is_an_allowlisted_reference_not_an_endpoint():
    assert ProfileReference().profile_id == "damon.mock"
    for data in ({"profile_id": "arbitrary"}, {"endpoint": "https://invalid.example"},
                 {"api_key": "FAKE_SECRET_FOR_TEST"}, {"secret_ref": "private"}):
        with pytest.raises(ValidationError):
            ProfileReference.model_validate(data)
    with pytest.raises(ValidationError):
        ResearchContext(market="CN", data_mode="simulation", as_of=datetime(2026, 10, 17))


def test_status_is_static_and_exposes_no_execution_endpoint(caplog):
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.get("/api/custom/damon/ai/status")
        payload = response.json()
        assert response.status_code == 200
        assert set(payload) == {"request_id", "phase", "demo_only", "profile_ids", "voice_modes",
                                "real_voice_available", "production_tools", "text_chat_available"}
        assert not payload["demo_only"] and payload["text_chat_available"]
        assert not payload["production_tools"] and not payload["real_voice_available"]
        assert client.post("/api/custom/damon/ai/tools").status_code == 404
    assert "api_key" not in response.text + caplog.text
