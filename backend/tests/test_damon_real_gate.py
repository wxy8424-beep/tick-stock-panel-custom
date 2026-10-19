"""Real gate refusal and explicit offline transport only. No live model or secrets."""
import asyncio
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import httpx
import openai
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import damon_ai
from app.services import ai_provider
from app.services.damon_ai import real_gate as gate
from app.services.damon_ai.chat import ChatRegistry, ChatRequest
from app.services.damon_ai.profiles import Profile, Snapshot

FAKE = "GATE_FIXTURE_NOT_A_REAL_CREDENTIAL"
MESSAGES = [{"role": "system", "content": "system"}, {"role": "user", "content": "hello"}]


def test_default_closed_and_no_operator_overrides(monkeypatch):
    report = gate.evaluate()
    assert not report.ready and not gate.Report().ready
    checks = {c.check_id: c.status for c in report.checks}
    assert checks[gate.CheckId.EGRESS] == checks[gate.CheckId.COST] == gate.Status.UNVERIFIED
    with pytest.raises(TypeError):
        gate.evaluate(operator_confirmed=True)
    for name in ("EGRESS_OK", "COST_CAP_VERIFIED", "REAL_MODEL_GATE_OPEN"):
        monkeypatch.setenv(name, "1")
    assert not gate.evaluate().ready
    assert all(c.status == gate.Status.UNVERIFIED for c in gate.evaluate().checks
               if c.check_id in {gate.CheckId.COST, gate.CheckId.EGRESS})


@pytest.mark.parametrize("endpoint", [
    "http://api.openai.com/v1", "https://localhost", "https://localhost.localdomain",
    "https://127.0.0.1", "https://10.0.0.1", "https://172.16.0.1", "https://192.168.1.1",
    "https://169.254.1.1", "https://0.0.0.0", "https://224.0.0.1", "https://8.8.8.8",
    "https://[::1]", "https://[fe80::1]", "https://[::]", "https://user:fake@api.openai.com",
    "https://api.openai.com.evil.invalid", "https://evil.invalid", "file:///v1", "ftp://api.openai.com",
    "https://[broken", "https://api.openai.com:bad", "https://api.openai.com:444",
    "https://api.openai.com//evil.invalid", "https://api.openai.com/%2f%2fevil.invalid",
    "https://api.openai.com?host=evil.invalid", "https://api.openai.com#evil",
    "https://api.openai.com\\@evil.invalid", "https://api.openai.com/../v1",
    "https://аpi.openai.com", "https://xn--api-9cd.openai.com", "https://api.openai.com..",
    "\nhttps://api.openai.com", "https://api.openai.com/\n", "", None,
])
def test_endpoint_fail_closed(endpoint):
    assert gate.endpoint_check(endpoint).status != gate.Status.PASS


@pytest.mark.parametrize("endpoint", ["https://api.openai.com", "https://API.OPENAI.COM/v1",
                                      "https://api.openai.com./v1/", "https://api.openai.com:443/v1"])
def test_canonical_allowlist(endpoint):
    assert gate.endpoint_check(endpoint).status == gate.Status.PASS


@pytest.mark.parametrize("char", ["中", "😀"])
@pytest.mark.parametrize("length", [999, 1000, 1001])
def test_new_input_unicode_boundary(char, length):
    result = gate.prompt_check([{"role": "user", "content": char * length}], 512)
    assert (result.status == gate.Status.PASS) == (length <= 1000)


@pytest.mark.parametrize("length", [2999, 3000, 3001])
@pytest.mark.parametrize("max_tokens", [511, 512, 513])
def test_full_context_and_output_boundaries(length, max_tokens):
    messages = [{"role": "system", "content": "中" * 1000},
                {"role": "assistant", "content": "😀" * (length - 2000)},
                {"role": "user", "content": "😀" * 1000}]
    assert (gate.prompt_check(messages, max_tokens).status == gate.Status.PASS) == (length <= 3000 and max_tokens <= 512)


@pytest.mark.parametrize("limits", [(4, 1), (3, 2), (0, 1), (True, 1), (3, True)])
def test_invalid_server_budget(limits):
    with pytest.raises(ValueError):
        gate.SmokeBudget(*limits)


def test_attempts_never_refund_and_close_permanently():
    budget = gate.SmokeBudget()
    for expected in range(1, 4):
        lease = budget.admit(MESSAGES, 512)
        assert budget.attempts == expected
        assert budget.finish(lease, gate.Outcome.SUCCESS)
        assert not budget.finish(lease, gate.Outcome.SUCCESS)
    assert budget.check().status == gate.Status.FAIL
    with pytest.raises(RuntimeError, match="closed"):
        budget.admit(MESSAGES, 512)


@pytest.mark.parametrize("outcome", [gate.Outcome.FAILURE, gate.Outcome.CANCELLED,
                                     gate.Outcome.TIMEOUT, gate.Outcome.UNCERTAIN])
def test_failure_cancel_timeout_close_runtime(outcome):
    budget = gate.SmokeBudget()
    lease = budget.admit(MESSAGES, 512)
    assert budget.finish(lease, outcome) and budget.attempts == 1
    with pytest.raises(RuntimeError, match="closed"):
        budget.admit(MESSAGES, 512)
    if outcome == gate.Outcome.UNCERTAIN:
        assert budget.finish(lease, gate.Outcome.SUCCESS)
        assert budget.check().status == gate.Status.FAIL


def test_thread_competition_reserves_only_one_attempt():
    budget, barrier = gate.SmokeBudget(), Barrier(12)
    def compete(_):
        barrier.wait(timeout=5)
        try:
            return budget.admit(MESSAGES, 512)
        except RuntimeError:
            return None
    with ThreadPoolExecutor(max_workers=12) as executor:
        leases = list(executor.map(compete, range(12)))
    assert sum(lease is not None for lease in leases) == budget.attempts == 1


async def test_async_competition_reserves_only_one_attempt():
    budget = gate.SmokeBudget()
    async def compete():
        await asyncio.sleep(0)
        try:
            return budget.admit(MESSAGES, 512)
        except RuntimeError:
            return None
    leases = await asyncio.gather(*(compete() for _ in range(12)))
    assert sum(lease is not None for lease in leases) == budget.attempts == 1


@pytest.mark.parametrize("base", ["https://api.openai.com/v1", None, "", 1])
def test_direct_factory_cannot_construct_sdk_or_inspect_key(base, monkeypatch, caplog):
    def forbidden(*args, **kwargs):
        raise AssertionError("SDK or transport constructed while closed")
    class Unreadable:
        def __str__(self):
            raise AssertionError("credential parsed")
        def __bool__(self):
            raise AssertionError("credential tested")
    monkeypatch.setattr(openai, "AsyncOpenAI", forbidden)
    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    import socket
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    with pytest.raises(gate.GateClosedError) as caught:
        ai_provider._openai_client(Unreadable(), 60, base_url=base)
    assert not caught.value.report.ready and str(caught.value) == "real_model_gate_closed"
    assert not caplog.records


@pytest.mark.parametrize("protocol", ["chat_completions", "responses"])
@pytest.mark.parametrize("model", ["normal", "different-model"])
async def test_stream_and_direct_snapshot_cannot_bypass(protocol, model, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("real client constructed")
    monkeypatch.setattr(openai, "AsyncOpenAI", forbidden)
    snapshot = Snapshot(Profile(profile_id="fixture", display_name="fixture", model=model, protocol=protocol),
                        "https://api.openai.com/v1", FAKE, "fixture", 512)
    manager = ChatRegistry()
    req = ChatRequest(profile_id="fixture", messages=[{"role": "user", "content": "hello"}])
    turn = manager.admit("fixture", req, snapshot)
    async def connected():
        return False
    events = [event async for event in manager.stream(turn, req, connected)]
    assert events[-1]["type"] == "error" and not any(e["type"] == "done" for e in events)
    with pytest.raises(gate.GateClosedError):
        _ = [text async for text in ai_provider.stream_snapshot_text(
            MESSAGES, api_key=FAKE, base_url=None, model=model, protocol=protocol,
            user_agent="fixture", max_tokens=512, timeout=60)]


def test_real_api_hits_gate_without_sdk_or_network(monkeypatch):
    from app.services import auth
    snapshot = Snapshot(Profile(profile_id="fixture", display_name="fixture", model="fixture", protocol="responses"),
                        "https://api.openai.com/v1", FAKE, "fixture", 512)
    monkeypatch.setattr(damon_ai.profiles, "resolve", lambda _: snapshot)
    monkeypatch.setattr(damon_ai, "registry", ChatRegistry())
    monkeypatch.setattr(auth, "is_configured", lambda: True)
    monkeypatch.setattr(auth, "is_valid_session", lambda token: token == "fixture-owner")
    called = []
    original = gate.require_real_client
    def observe():
        called.append(True)
        original()
    monkeypatch.setattr(gate, "require_real_client", observe)
    def forbidden(*args, **kwargs):
        raise AssertionError("SDK reached")
    monkeypatch.setattr(openai, "AsyncOpenAI", forbidden)
    app = FastAPI()
    app.include_router(damon_ai.router)
    with TestClient(app, cookies={"tf_session": "fixture-owner"}) as client:
        response = client.post("/api/custom/damon/ai/chat", json={
            "profile_id": "fixture", "messages": [{"role": "user", "content": "hello"}]})
    assert called == [True]
    assert response.status_code == 200 and '"type": "done"' not in response.text
    assert '"type": "error"' in response.text and FAKE not in response.text


async def test_offline_sdk_512_mapping_and_proxy_independence(monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.setenv(name, "http://proxy.invalid:9999")
    def forbidden(*args, **kwargs):
        raise AssertionError("fake transport entered real gate or env proxy resolution")
    monkeypatch.setattr(gate, "require_real_client", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "_get_proxy_map", lambda self, proxy, allow_env_proxies: (
        {} if proxy is None and allow_env_proxies is False else forbidden()))
    for protocol in ("chat_completions", "responses"):
        seen = []
        async def respond(request, seen=seen, protocol=protocol):
            seen.append(json.loads(request.content))
            event = ({"type": "response.completed", "response": {"status": "completed"}} if protocol == "responses"
                     else {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
            delta = ({"type": "response.output_text.delta", "delta": "answer"} if protocol == "responses"
                     else {"choices": [{"index": 0, "delta": {"content": "answer"}, "finish_reason": None}]})
            return httpx.Response(200, headers={"Content-Type": "text/event-stream"},
                                  content="data: " + json.dumps(delta) + "\n\ndata: " + json.dumps(event) + "\n\n")
        client = ai_provider._openai_client(FAKE, 1, base_url="https://offline.invalid/v1",
                                           offline_transport=httpx.MockTransport(respond))
        assert client.max_retries == 0 and client._client._trust_env is False
        assert client._client.follow_redirects is False
        await client.close()
        _ = [text async for text in ai_provider.stream_snapshot_text(
            MESSAGES, api_key=FAKE, base_url="https://offline.invalid/v1", model="fixture", protocol=protocol,
            user_agent="fixture", max_tokens=512, timeout=1, offline_transport=httpx.MockTransport(respond))]
        assert "".join(_) == "answer"
        assert seen[0]["max_output_tokens" if protocol == "responses" else "max_tokens"] == 512


def test_legacy_factory_does_not_enter_gate(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("legacy entered Damon gate")
    monkeypatch.setattr(gate, "require_real_client", forbidden)
    monkeypatch.setattr(ai_provider.secrets_store, "get_ai_config", lambda name, fallback: fallback)
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kwargs: kwargs)
    result = ai_provider._openai_client(FAKE, 1)
    assert result["max_retries"] == 2 and "http_client" not in result


@pytest.mark.parametrize("case", ["local", "missing_data", "production_data", "env", "reload", "workers", "main"])
def test_real_bootstrap_observations_remain_closed(case):
    script = r'''
import sys, os, json
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'scripts'))
from damon_offline import Sandbox
with Sandbox() as sandbox:
    data = sandbox.root / 'data'
    data.mkdir()
    from app.services.damon_ai import real_gate as gate
    case = sys.argv[1]
    if case == 'missing_data': os.environ.pop('DATA_DIR')
    if case == 'production_data': os.environ['DATA_DIR'] = str(Path.cwd().parent / 'data')
    if case == 'env': os.environ['TICKFLOW_ENV_FILE'] = str(Path.cwd().parent / '.env')
    if case == 'reload': sys.argv.append('--reload')
    if case == 'workers': os.environ['WEB_CONCURRENCY'] = '2'
    if case == 'main': sys.modules['app.main'] = object()
    report = gate.evaluate(endpoint=gate.REFERENCE_ENDPOINT, credential_ref=('existing_ai', 'ai_api_key'),
        budget=gate.SmokeBudget(), messages=[{'role':'user', 'content':'hello'}])
    result = report.to_dict()
result['cleaned'] = not sandbox.root.exists()
print(json.dumps(result))
'''
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "PATH", "TEMP", "TMP") if key in os.environ}
    result = subprocess.run([sys.executable, "-B", "-c", script, case], env=env,
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert not report["ready"] and report["cleaned"]
    checks = {c["check_id"]: c["status"] for c in report["checks"]}
    assert checks["OS_EGRESS"] == checks["COST_CAP"] == "UNVERIFIED"
    assert checks["EXECUTION_ISOLATION"] == ("PASS" if case == "local" else "FAIL")
    if case == "local":
        assert all(status == "PASS" for key, status in checks.items() if key not in {"OS_EGRESS", "COST_CAP"})


def test_preflight_no_sdk_or_secret_modules():
    script = Path(__file__).resolve().parents[1] / "scripts/damon_real_preflight.py"
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "PATH", "TEMP", "TMP") if key in os.environ}
    result = subprocess.run([sys.executable, "-B", str(script)], env=env,
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 2, result.stderr
    report = json.loads(result.stdout)
    assert report["REAL-MODEL-GATE"] == "CLOSED" and report["REAL MODEL SMOKE"] == "NO-GO"
    assert report["cleanup_complete"] and not report["ready"]
    assert FAKE not in result.stdout + result.stderr
