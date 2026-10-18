"""Phase 1.2 fake model and isolated HTTP contracts; no production configuration."""
import asyncio
import json
import socket
import sqlite3
import subprocess
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import damon_ai
from app.services import ai_provider
from app.services.damon_ai import profiles
from app.services.damon_ai.chat import ChatRegistry, ChatRequest
from app.services.damon_ai.profiles import ChatError

KEY = "FAKE_CREDENTIAL_ONLY_FOR_OFFLINE_TEST"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("external operation forbidden")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(profiles.secrets_store, "load", lambda: config())
    # Empty store credentials must test an explicitly unconfigured fallback,
    # regardless of preceding tests or the runner environment. Undo on teardown.
    monkeypatch.setattr(profiles.settings, "ai_api_key", "")


def config():
    return {"ai_provider": "openai_compat", "ai_base_url": "https://model.example/v1",
            "ai_api_key": KEY, "ai_model": "legacy", "ai_protocol": "chat_completions",
            "damon_profiles": [dict(profile_id=name, display_name=name, model=name,
                                    protocol="chat_completions") for name in ("alpha", "beta")]}


def req(profile="alpha", cid=None):
    return ChatRequest(profile_id=profile, conversation_id=cid,
                       messages=[{"role": "user", "content": "hello"}])


async def connected():
    return False


@pytest.mark.parametrize("character", ["中", "😀"])
@pytest.mark.parametrize("length", [15999, 16000, 16001])
async def test_unicode_body_budget_uses_code_points_and_never_succeeds_after_overflow(
        character, length, monkeypatch):
    text = character * length

    async def fake(messages, **kwargs):
        # Cross the limit cumulatively, not just in one oversized provider delta.
        yield text[:8000]
        yield text[8000:16000]
        yield text[16000:]

    monkeypatch.setattr(ai_provider, "stream_snapshot_text", fake)
    manager = ChatRegistry()
    turn = manager.admit("actor", req(), profiles.resolve("alpha"))
    events = [e async for e in manager.stream(turn, req(), connected)]
    actual = "".join(e.get("text", "") for e in events)
    if length <= 16000:
        assert actual == text
        assert events[-1]["type"] == "done"
    else:
        assert len(actual) <= 16000
        assert events[-1]["type"] == "error" and events[-1]["code"] == "output_limit"
        assert not any(e["type"] == "done" for e in events)
    assert turn.task.done()
    # Task done callbacks run on the next loop tick, not inside queue.get().
    await asyncio.sleep(0)
    assert not manager.active


@pytest.mark.parametrize("change", ["missing", "disabled", "capability"])
def test_profile_denials(change, monkeypatch):
    data = config()
    if change == "disabled":
        data["damon_profiles"][0]["enabled"] = False
    if change == "capability":
        data["damon_profiles"][0]["text_stream"] = False
    monkeypatch.setattr(profiles.secrets_store, "load", lambda: data)
    with pytest.raises(ChatError):
        profiles.resolve("missing" if change == "missing" else "alpha")


async def test_redaction_expansion_cannot_exceed_delivered_body_budget(monkeypatch):
    data = config()
    data["ai_api_key"] = "FAKE"
    monkeypatch.setattr(profiles.secrets_store, "load", lambda: data)

    async def fake(messages, **kwargs):
        yield "FAKE" * 3000  # 12000 input points, 30000 after redaction.

    monkeypatch.setattr(ai_provider, "stream_snapshot_text", fake)
    manager = ChatRegistry()
    turn = manager.admit("actor", req(), profiles.resolve("alpha"))
    events = [e async for e in manager.stream(turn, req(), connected)]
    assert events[-1]["type"] == "error" and events[-1]["code"] == "output_limit"
    assert not any(e["type"] == "done" for e in events)
    assert len("".join(e.get("text", "") for e in events)) <= 16000


@pytest.mark.parametrize("base", ["http://model.example", "https://user:pass@model.example",
                                      "https://model.example/?key=FAKE", "https://model.example/#secret"])
def test_endpoint_admission(base, monkeypatch):
    data = config()
    data["ai_base_url"] = base
    monkeypatch.setattr(profiles.secrets_store, "load", lambda: data)
    with pytest.raises(ChatError, match="unsafe_endpoint"):
        profiles.resolve("alpha")


def test_snapshot_and_metadata_do_not_mutate_legacy_or_expose_refs(monkeypatch):
    data = config()
    monkeypatch.setattr(profiles.secrets_store, "load", lambda: data)
    first = profiles.resolve("alpha")
    data["damon_profiles"][0]["model"] = "changed"
    second = profiles.resolve("beta")
    assert first.profile.model == "alpha" and second.profile.model == "beta"
    assert ai_provider.current_ai_model() == "legacy"
    assert KEY not in repr(first) + json.dumps(profiles.metadata())
    assert not any("ref" in key for p in profiles.metadata() for key in p)


def test_unconfigured_and_sensitive_profile_metadata_fail_closed(monkeypatch):
    data = config()
    data["ai_api_key"] = ""
    monkeypatch.setattr(profiles.secrets_store, "load", lambda: data)
    assert not any(p["configured"] for p in profiles.metadata())
    with pytest.raises(ChatError, match="not_configured"):
        profiles.resolve("alpha")
    data["ai_api_key"] = KEY
    data["damon_profiles"][0]["display_name"] = KEY
    with pytest.raises(ChatError, match="profile_configuration"):
        profiles.metadata()


def test_legacy_default_profile_and_explicit_unsupported_protocol(monkeypatch):
    data = config()
    del data["damon_profiles"]
    data["ai_protocol"] = "invalid-legacy-value"
    monkeypatch.setattr(profiles.secrets_store, "load", lambda: data)
    assert profiles.resolve("damon.default").profile.protocol == "chat_completions"
    data["ai_provider"] = "codex_cli"
    with pytest.raises(ChatError, match="profile_unavailable"):
        profiles.resolve("damon.default")
    data["damon_profiles"] = [{"profile_id": "bad", "display_name": "bad", "model": "bad", "protocol": "realtime"}]
    with pytest.raises(ChatError, match="profile_configuration"):
        profiles.resolve("bad")


async def test_parallel_snapshots_and_cross_chunk_secret_redaction(monkeypatch):
    captured = []
    async def fake(messages, **kwargs):
        captured.append(kwargs["model"])
        yield KEY[:12]
        await asyncio.sleep(0)
        yield KEY[12:] + "hello"
    monkeypatch.setattr(ai_provider, "stream_snapshot_text", fake)
    manager = ChatRegistry()
    turns = [manager.admit("actor", req(p), profiles.resolve(p)) for p in ("alpha", "beta")]
    async def collect(turn, p):
        return [e async for e in manager.stream(turn, req(p), connected)]
    results = await asyncio.gather(*(collect(t, p) for t, p in zip(turns, ("alpha", "beta"), strict=True)))
    assert sorted(captured) == ["alpha", "beta"]
    for events in results:
        assert events[-1]["type"] == "done"
        assert KEY not in json.dumps(events)
        assert "".join(e.get("text", "") for e in events) == "[redacted]hello"
    assert not manager.active


@pytest.mark.parametrize("condition", ["timeout", "cancel", "disconnect", "error", "output_limit", "transport_timeout"])
async def test_terminal_failures_never_report_success(condition, monkeypatch, caplog):
    started = asyncio.Event()
    async def fake(messages, **kwargs):
        started.set()
        if condition == "error":
            raise RuntimeError(KEY + " https://private.example/raw-error")
        if condition == "transport_timeout":
            raise httpx.ReadTimeout(KEY)
        if condition == "output_limit":
            yield "x" * 16001
        else:
            await asyncio.Event().wait()
            yield "late"
    monkeypatch.setattr(ai_provider, "stream_snapshot_text", fake)
    manager = ChatRegistry(timeout=0.03)
    turn = manager.admit("actor", req(), profiles.resolve("alpha"))
    async def disconnected():
        return condition == "disconnect" and started.is_set()
    async def collect():
        return [e async for e in manager.stream(turn, req(), disconnected)]
    task = asyncio.create_task(collect())
    await started.wait()
    if condition == "cancel":
        manager.cancel("actor", turn.conversation_id, turn.turn_id)
    events = await task
    assert events[-1]["type"] in {"error", "cancelled"}
    assert not any(e["type"] == "done" or e.get("text") == "late" for e in events)
    assert KEY not in json.dumps(events) + caplog.text
    assert "private.example" not in json.dumps(events) + caplog.text
    assert not manager.active


async def test_explicit_client_disables_redirects_and_retries_without_reading_defaults(monkeypatch):
    import openai
    def forbidden():
        raise AssertionError("explicit configuration must not read global defaults")
    monkeypatch.setattr(profiles.secrets_store, "load", forbidden)
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kwargs: SimpleNamespace(**kwargs))
    client = ai_provider._openai_client(KEY, 1, base_url="https://model.example/v1", user_agent="test")
    try:
        assert client.max_retries == 0 and client.http_client.follow_redirects is False
        assert client.api_key == KEY
    finally:
        await client.http_client.aclose()


async def test_uncooperative_cancel_holds_admission_until_actual_exit(monkeypatch):
    release, started = asyncio.Event(), asyncio.Event()
    async def fake(messages, **kwargs):
        started.set()
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                continue
        yield "late"
    monkeypatch.setattr(ai_provider, "stream_snapshot_text", fake)
    manager = ChatRegistry(cleanup=0.01)
    turn = manager.admit("actor", req(), profiles.resolve("alpha"))
    stream = manager.stream(turn, req(), connected)
    await anext(stream)
    await started.wait()
    manager.cancel("actor", turn.conversation_id, turn.turn_id)
    assert await manager.stop(turn) == "still_running"
    with pytest.raises(ChatError, match="busy"):
        manager.admit("actor", req(cid=turn.conversation_id), profiles.resolve("alpha"))
    release.set()
    assert (await anext(stream))["type"] == "cancelled"
    await stream.aclose()
    await asyncio.sleep(0)
    assert not manager.active and turn.owner.calls == 1


def test_identity_budget_and_new_conversations_cannot_reset_actor_budget():
    manager = ChatRegistry()
    snapshot = profiles.resolve("alpha")
    first = manager.admit("one", req(), snapshot)
    with pytest.raises(ChatError, match="conversation_unavailable"):
        manager.admit("two", req(cid=first.conversation_id), snapshot)
    with pytest.raises(ChatError, match="turn_unavailable"):
        manager.cancel("two", first.conversation_id, first.turn_id)
    manager.release(first)
    first.owner.calls = 20
    with pytest.raises(ChatError, match="budget"):
        manager.admit("one", req(cid=first.conversation_id), snapshot)
    manager.admissions["one"] = (first.owner.touched, 60)
    with pytest.raises(ChatError, match="budget"):
        manager.admit("one", req(), snapshot)


def test_busy_requests_do_not_allocate_unreachable_conversations():
    manager = ChatRegistry()
    snapshot = profiles.resolve("alpha")
    turns = [manager.admit("actor", req(), snapshot) for _ in range(2)]
    for _ in range(5):
        with pytest.raises(ChatError, match="busy"):
            manager.admit("actor", req(), snapshot)
    assert len(manager.conversations) == 2 and len(manager.active) == 2
    for turn in turns:
        manager.release(turn)


def test_http_contract_no_endpoint_override_and_safe_errors(monkeypatch):
    monkeypatch.setattr(damon_ai, "actor", lambda request: "test")
    monkeypatch.setattr(damon_ai, "registry", ChatRegistry())
    async def fake(messages, **kwargs):
        yield "answer"
    monkeypatch.setattr(ai_provider, "stream_snapshot_text", fake)
    app = FastAPI()
    app.include_router(damon_ai.router)
    with TestClient(app) as client:
        for extra in ({"endpoint": "https://bad.example"}, {"api_key": KEY}, {"credential_ref": KEY}):
            response = client.post("/api/custom/damon/ai/chat", json={**req().model_dump(), **extra})
            assert response.status_code == 400 and KEY not in response.text
        result = client.post("/api/custom/damon/ai/chat", json=req().model_dump())
        events = [json.loads(line) for line in result.text.splitlines()]
        assert [e["type"] for e in events] == ["start", "delta", "done"]
        assert events[0]["profile_id"] == "alpha"
        assert set(events[0]) == {"type", "profile_id", "sequence", "request_id", "turn_id", "conversation_id"}
        assert KEY not in client.get("/api/custom/damon/ai/profiles").text
        sensitive = req().model_dump()
        sensitive["messages"][0]["content"] = KEY
        rejected = client.post("/api/custom/damon/ai/chat", json=sensitive)
        assert rejected.json()["code"] == "sensitive_input" and KEY not in rejected.text
        assert client.post("/api/custom/damon/ai/chat", content="x" * 65000).json()["code"] == "input_limit"
        long_history = req().model_dump()
        long_history["messages"] = [{"role": "user", "content": "before"},
                                    {"role": "assistant", "content": "x" * 9000},
                                    {"role": "user", "content": "continue"}]
        assert client.post("/api/custom/damon/ai/chat", json=long_history).text.endswith('"code": "completed"}\n')


def test_cost_endpoints_fail_closed_without_authenticated_owner(monkeypatch):
    from app.services import auth
    monkeypatch.setattr(auth, "is_configured", lambda: True)
    monkeypatch.setattr(auth, "is_valid_session", lambda token: False)
    app = FastAPI()
    app.include_router(damon_ai.router)
    with TestClient(app) as client:
        assert client.get("/api/custom/damon/ai/profiles").status_code == 403
        assert client.post("/api/custom/damon/ai/chat", json=req().model_dump()).status_code == 403


def test_cookie_owner_is_verified_and_bearer_cannot_bypass_cost_gate(monkeypatch):
    from app.services import auth
    monkeypatch.setattr(auth, "is_configured", lambda: True)
    monkeypatch.setattr(auth, "is_valid_session", lambda token: token == "fake-owner-session")
    app = FastAPI()
    app.include_router(damon_ai.router)
    with TestClient(app, cookies={"tf_session": "fake-owner-session"}) as client:
        assert client.get("/api/custom/damon/ai/profiles").status_code == 200
        assert client.get("/api/custom/damon/ai/profiles", headers={"Authorization": "Bearer FAKE"}).status_code == 403


@pytest.mark.parametrize("protocol", ["chat_completions", "responses"])
@pytest.mark.parametrize("terminal", [True, False])
@pytest.mark.parametrize("trailing_error", [True, False])
async def test_explicit_adapter_reuses_parsers_requires_terminal_and_closes_resources(
        protocol, terminal, trailing_error, monkeypatch):
    closed, captured = [], []
    class Stream:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            closed.append("stream")
        async def __aiter__(self):
            if protocol == "responses":
                yield SimpleNamespace(type="response.output_text.delta", delta="answer")
                if terminal:
                    yield SimpleNamespace(type="response.completed", response=SimpleNamespace(status="completed"))
                if trailing_error:
                    yield SimpleNamespace(type="error", error=None)
            else:
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="answer"), finish_reason=None)])
                if terminal:
                    yield SimpleNamespace(choices=[SimpleNamespace(delta=None, finish_reason="stop")])
                if trailing_error:
                    yield SimpleNamespace(choices=[SimpleNamespace(delta=None, finish_reason="content_filter")])
    async def create(**kwargs):
        assert "tools" not in kwargs
        captured.append(kwargs)
        return Stream()
    class Client:
        chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        responses = SimpleNamespace(create=create)
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            closed.append("client")
    def client(key, timeout, **kwargs):
        assert key == KEY and kwargs["base_url"] == "https://model.example/v1"
        return Client()
    monkeypatch.setattr(ai_provider, "_openai_client", client)
    async def consume():
        return [d async for d in ai_provider.stream_snapshot_text(
            [{"role": "user", "content": "hello"}], api_key=KEY, base_url="https://model.example/v1",
            model="explicit", protocol=protocol, user_agent="test", max_tokens=10, timeout=1)]
    if terminal and not trailing_error:
        assert await consume() == ["answer"]
    else:
        with pytest.raises(RuntimeError, match="incomplete_stream"):
            await consume()
    assert captured[0]["model"] == "explicit"
    assert closed == ["stream", "client"]
