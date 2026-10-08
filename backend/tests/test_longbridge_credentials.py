"""隔离本地 secret 文件与 mock SDK 的设置 API 行为测试。"""
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import secrets_store
from app.api.settings import router
from app.plugins.longbridge import provider as lb

FIELDS = ("app_key", "app_secret", "access_token")
BUNDLE = {field: f"fake-longbridge-{field}-testing-only" for field in FIELDS}
STORED = {f"longbridge_{field}": value for field, value in BUNDLE.items()}


@pytest.fixture
def environment(monkeypatch, tmp_path):
    from app import config
    from app.data_providers import custom

    path = tmp_path / "secrets.json"
    monkeypatch.setattr(secrets_store, "_path", lambda: path)
    monkeypatch.setattr(secrets_store, "_cache", None)
    monkeypatch.setattr(secrets_store, "_cache_sig", None)
    monkeypatch.setattr(config, "_ENV_FILE", tmp_path / ".env")
    for name in lb._ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    calls = []

    class Context:
        def __init__(self, credentials):
            calls.append(("context", credentials))

        def quote(self, symbols):
            calls.append(("quote", symbols))
            return [SimpleNamespace(symbol="700.HK", last_done=10)]

    sdk = SimpleNamespace(Config=SimpleNamespace(from_apikey=lambda *args, **kwargs: args), QuoteContext=Context)
    monkeypatch.setattr(lb, "_sdk", lambda: sdk)
    monkeypatch.setattr(custom, "load_all", lambda: calls.append(("reload", None)))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), path, calls, sdk, tmp_path


@pytest.mark.parametrize("missing", FIELDS)
def test_missing_candidate_does_not_save(environment, missing):
    client, path, calls, _, _ = environment
    response = client.post("/api/settings/longbridge-credentials", json={k: v for k, v in BUNDLE.items() if k != missing})
    assert response.json() == {"ok": False, "reason": "unconfigured"}
    assert not path.exists() and not calls


def test_authentication_failure_no_write_or_disclosure(environment, monkeypatch, caplog):
    client, path, calls, sdk, _ = environment

    def fail(config):
        raise RuntimeError("unauthorized fake-longbridge-access_token-testing-only")

    monkeypatch.setattr(sdk, "QuoteContext", fail)
    result = client.post("/api/settings/longbridge-credentials", json=BUNDLE)
    assert result.json() == {"ok": False, "reason": "authentication"}
    assert not path.exists() and not calls
    assert BUNDLE["access_token"] not in result.text + caplog.text


def test_success_saves_complete_bundle_then_reloads(environment):
    client, path, calls, _, _ = environment
    secrets_store.save({"unrelated": "keep"})
    result = client.post("/api/settings/longbridge-credentials", json=BUNDLE)
    assert result.json()["ok"] is True
    assert json.loads(path.read_text()) == {"unrelated": "keep", **STORED}
    assert calls == [("context", tuple(BUNDLE.values())), ("quote", ["700.HK"]), ("reload", None)]
    assert all(value not in result.text for value in BUNDLE.values())
    state = client.get("/api/settings/longbridge-credentials")
    assert state.json() == {"app_key_masked": secrets_store.mask(BUNDLE["app_key"]),
                            "app_secret_configured": True, "access_token_configured": True,
                            "status": "available"}
    assert all(value not in state.text for value in BUNDLE.values())


def test_atomic_write_failure_preserves_old_bundle(environment, monkeypatch):
    client, path, _, _, _ = environment
    old = {field: "fake-old-" + field for field in STORED}
    secrets_store.save(old)
    before = path.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("fake write failure")

    monkeypatch.setattr(secrets_store, "atomic_write_text", fail)
    assert client.post("/api/settings/longbridge-credentials", json=BUNDLE).json()["reason"] == "storage_error"
    assert path.read_bytes() == before


def test_stored_bundle_priority_and_no_partial_mix(environment, monkeypatch):
    for name in lb._ENV_NAMES:
        monkeypatch.setenv(name, "fake-environment-" + name)
    secrets_store.save(STORED)
    assert lb._credentials() == tuple(BUNDLE.values())
    secrets_store.clear("longbridge_app_secret")
    assert lb._credentials()[1] == ""
    assert lb.availability()[0] is False


def test_env_and_dotenv_fallback(environment, monkeypatch):
    _, _, _, _, root = environment
    (root / ".env").write_text("\n".join(f"{name}=fake-dotenv-{i}" for i, name in enumerate(lb._ENV_NAMES)))
    assert lb._credentials() == tuple(f"fake-dotenv-{i}" for i in range(3))
    monkeypatch.setenv(lb._ENV_NAMES[0], "fake-process-env")
    assert lb._credentials()[0] == "fake-process-env"


def test_clear_removes_all_three_retains_other_secrets(environment):
    client, path, calls, _, _ = environment
    secrets_store.save({**STORED, "unrelated": "keep"})
    assert client.delete("/api/settings/longbridge-credentials").json()["status"] == "unconfigured"
    assert json.loads(path.read_text()) == {"unrelated": "keep"}
    assert calls == [("reload", None)]


def test_validation_never_echoes_candidate_values(environment):
    client, _, _, _, _ = environment
    for payload in ({**BUNDLE, "app_key": [BUNDLE["app_key"]]}, list(BUNDLE.values())):
        response = client.post("/api/settings/longbridge-credentials", json=payload)
        assert response.json() == {"ok": False, "reason": "invalid_request"}
        assert all(value not in response.text for value in BUNDLE.values())


def test_sdk_missing_no_save(environment, monkeypatch):
    client, path, _, _, _ = environment

    def missing():
        raise ImportError("fake missing SDK")

    monkeypatch.setattr(lb, "_sdk", missing)
    assert client.post("/api/settings/longbridge-credentials", json=BUNDLE).json()["reason"] == "sdk_missing"
    assert client.get("/api/settings/longbridge-credentials").json()["status"] == "sdk_missing"
    assert not path.exists()


def test_concurrent_bundle_saves_are_not_partial(environment):
    _, path, _, _, _ = environment
    alternatives = [{field: f"fake-{generation}-{field}" for field in STORED} for generation in range(8)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(secrets_store.save, alternatives))
    assert json.loads(path.read_text()) in alternatives
