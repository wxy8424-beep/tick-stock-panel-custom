"""Fresh child processes: no application import before the isolated bootstrap."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


async def exercise(case, sandbox):
    import asyncio

    from damon_offline_app import FakeModel, OfflineRuntime, request

    mode = {"failure": "error", "cancel": "hold", "disconnect": "hold",
            "shutdown": "hold", "timeout": "hold", "uncertain": "uncooperative"}.get(case, "success")
    text = {"output": "中" * 513, "output_boundary": "😀" * 512}.get(case, "OFFLINE_REPLY")
    runtime = OfflineRuntime(FakeModel(mode, text))
    base = "/api/custom/damon/ai"

    async def send(client, **kwargs):
        return await client.post(base + "/chat", json=request(**kwargs))

    def events(response):
        assert response.status_code == 200
        return [json.loads(line) for line in response.text.splitlines()]

    async with runtime.app.router.lifespan_context(runtime.app), runtime.client() as client:
        assert runtime.registry.timeout == 60
        assert (await client.get(base + "/profiles")).status_code == 401
        wrong = await client.post("/api/auth/login", json={"password": "wrong-fixture-password"})
        assert wrong.status_code == 401
        login = await client.post("/api/auth/login", json={"password": runtime.password})
        assert login.status_code == 200
        assert (await client.get("/api/auth/status")).json()["authenticated"]
        assert "httponly" in login.headers["set-cookie"].lower()
        assert runtime.password not in (sandbox.root / "data/user_data/auth.json").read_text()
        if case == "auth":
            for path in ("/api/auth/setup", "/api/auth/change-password", "/api/pipeline/run",
                         "/api/settings", "/api/anomalies", "/openapi.json", "/docs"):
                assert (await client.get(path)).status_code == 404
                assert (await client.post(path, json={})).status_code == 404
            assert (await client.get(base + "/profiles")).status_code == 200
            assert (await client.get(base + "/status")).status_code == 200
            assert (await client.get(base + "/profiles", headers={"Authorization": "Bearer FAKE"})).status_code == 401
            assert (await client.post("/api/auth/logout")).status_code == 200
            assert (await client.get(base + "/profiles")).status_code == 401
        elif case == "success":
            first = events(await send(client))
            assert first[-1]["type"] == "done"
            cid = first[0]["conversation_id"]
            second = events(await send(client, conversation_id=cid, messages=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "OFFLINE_REPLY"},
                {"role": "user", "content": "continue"}]))
            assert second[-1]["type"] == "done"
            assert runtime.model.calls[-1][0][-3:][1]["content"] == "OFFLINE_REPLY"
            assert events(await send(client))[-1]["type"] == "done"
            assert (await send(client)).json()["code"] == "offline_halted"
            assert len(runtime.model.calls) == runtime.registry.attempts == 3
            assert all(max_tokens == 512 for _, max_tokens in runtime.model.calls)
        elif case == "input":
            assert (await send(client, content="😀" * 1001)).json()["code"] == "input_limit"
            over = [{"role": "user", "content": "中" * 1000},
                    {"role": "assistant", "content": "😀" * 1001},
                    {"role": "user", "content": "😀" * 1000}]
            assert (await send(client, messages=over)).json()["code"] == "input_limit"
            assert runtime.registry.attempts == 0
            assert events(await send(client))[-1]["type"] == "done"
            system_length = len(runtime.model.calls[0][0][0]["content"])
            over[1]["content"] = "😀" * (1000 - system_length)
            assert events(await send(client, messages=over))[-1]["type"] == "done"
            assert sum(len(m["content"]) for m in runtime.model.calls[-1][0]) == 3000
        elif case == "full_context":
            over = [{"role": "user", "content": "中" * 1000},
                    {"role": "assistant", "content": "😀" * 1000},
                    {"role": "user", "content": "😀" * 1000}]
            result = events(await send(client, messages=over))
            assert result[-1]["type"] == "error" and result[-1]["code"] == "input_limit"
            assert not runtime.model.calls
            assert (await send(client)).json()["code"] == "offline_halted"
        elif case == "output_boundary":
            result = events(await send(client))
            assert result[-1]["type"] == "done"
            assert "".join(e.get("text", "") for e in result) == "😀" * 512
            assert runtime.model.calls[0][1] == 512
        elif case in {"failure", "output", "timeout"}:
            response = await send(client)
            result = events(response)
            assert result[-1]["type"] == "error"
            expected = {"failure": "upstream_error", "output": "output_limit", "timeout": "timeout"}[case]
            assert result[-1]["code"] == expected
            assert not any(e["type"] == "done" for e in result)
            assert "FAKE_PRIVATE_ERROR" not in response.text
            assert (await send(client)).json()["code"] == "offline_halted"
            assert runtime.registry.attempts == len(runtime.model.calls) == 1
        elif case in {"cancel", "uncertain"}:
            pending = asyncio.create_task(send(client))
            await runtime.model.started.wait()
            assert (await send(client)).json()["code"] == "busy"
            assert runtime.registry.attempts == 1
            turn = next(iter(runtime.registry.active.values()))
            response = await client.post(base + "/cancel", json={
                "conversation_id": turn.conversation_id, "turn_id": turn.turn_id})
            assert response.json()["cleanup_state"] == ("still_running" if case == "uncertain" else "finished")
            result = events(await pending)
            assert result[-1]["type"] == "cancelled", [(e["type"], e.get("code")) for e in result]
            assert not any(e["type"] == "done" for e in result)
            assert (await send(client)).json()["code"] == "offline_halted"
            runtime.model.release.set()
        elif case == "disconnect":
            # Real ASGI disconnect at the HTTP boundary, not just a fake UI Abort.
            payload = json.dumps(request()).encode()
            receives = 0
            async def receive():
                nonlocal receives
                receives += 1
                if receives == 1:
                    return {"type": "http.request", "body": payload, "more_body": False}
                await runtime.model.started.wait()
                return {"type": "http.disconnect"}
            sent = []
            async def capture(message):
                sent.append(message)
            cookie = client.cookies.get("tf_session")
            await runtime.app({"type": "http", "asgi": {"version": "3.0", "spec_version": "2.0"},
                               "http_version": "1.1", "method": "POST", "scheme": "http",
                               "path": base + "/chat", "raw_path": (base + "/chat").encode(),
                               "query_string": b"", "root_path": "", "server": ("127.0.0.1", 1),
                               "client": ("127.0.0.1", 1), "headers": [
                                   (b"content-type", b"application/json"),
                                   (b"cookie", ("tf_session=" + cookie).encode())]}, receive, capture)
            # A disconnected response can return before the producer's done
            # callback. Observe bounded completion, never cancel it to pass.
            work = {t.task for t in runtime.registry.active.values() if t.task is not None}
            if work:
                _, pending = await asyncio.wait(work, timeout=1)
                assert not pending
            await asyncio.sleep(0)
            assert not runtime.registry.active and runtime.registry.attempts == 1
            assert not any(b'"type": "done"' in m.get("body", b"") for m in sent)
            assert (await send(client)).json()["code"] == "offline_halted"
        elif case == "shutdown":
            from app.services.damon_ai.chat import ChatRequest
            from app.services.damon_ai.profiles import resolve

            req = ChatRequest.model_validate(request())
            turn = runtime.registry.admit("fixture", req, resolve("damon.default"))
            async def connected():
                return False
            stream = runtime.registry.stream(turn, req, connected)
            await anext(stream)
            await runtime.model.started.wait()
            # Leave an in-flight model for lifespan's real cleanup.
        elif case == "guards":
            import importlib
            import socket

            from app.services import ai_provider

            def connect():
                with socket.socket() as sock:
                    sock.connect(("203.0.113.1", 443))
            for action in (lambda: socket.getaddrinfo("offline.invalid", 443),
                           connect,
                           lambda: (sandbox.root.parent / "must-not-write").write_text("blocked"),
                           lambda: importlib.import_module("app.main"),
                           lambda: importlib.import_module("app.services.quote_service"),
                           lambda: subprocess.run([sys.executable, "-V"], check=True)):
                try:
                    action()
                except (PermissionError, ImportError):
                    pass
                else:
                    raise AssertionError("guard did not reject operation")
            repo = Path(__file__).resolve().parents[2]
            for path in (sandbox.root.parent / ".env", repo / ".ENV", repo / "SECRETS.JSON",
                         repo / "data" / "blocked", repo / "DATA" / "blocked"):
                try:
                    path.read_text()
                except PermissionError:
                    pass
                else:
                    raise AssertionError("credential/data file read not blocked")
            try:
                ai_provider._openai_client("FAKE", 1)
            except RuntimeError as exc:
                assert str(exc) == "real_sdk_forbidden"
            else:
                raise AssertionError("SDK fallback allowed")
        else:
            raise AssertionError("unknown case")
    if case == "shutdown":
        await stream.aclose()
    await asyncio.sleep(0)
    assert not runtime.registry.active
    assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
    assert not any(name == p or name.startswith(p + ".")
                   for name in sys.modules for p in sandbox.blocked_imports)
    return {"attempts": runtime.registry.attempts,
            "files": sorted(str(p.relative_to(sandbox.root)) for p in sandbox.root.rglob("*") if p.is_file()),
            "denied": sandbox.denied}


def child(case):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from damon_offline import Sandbox

    class FailingBootstrap(Sandbox):
        def _install_guards(self):
            raise RuntimeError("intentional_bootstrap_failure")

    sandbox = FailingBootstrap() if case == "enter_failure" else Sandbox()
    expected_failure = case in {"init_failure", "enter_failure", "test_failure", "bind_failure"}
    try:
        with sandbox:
            assert set(os.environ) <= {"SYSTEMROOT", "WINDIR", "PATH", "DATA_DIR", "TICKFLOW_ENV_FILE",
                                       "TEMP", "TMP", "HOME", "USERPROFILE", "AI_API_KEY", "TICKFLOW_API_KEY",
                                       "AUTH_PASSWORD", "WEB_CONCURRENCY", "PYTHONDONTWRITEBYTECODE"}
            assert not any(value == "INHERITED_FAKE_SECRET" for value in os.environ.values())
            if case == "init_failure":
                raise RuntimeError("intentional_initialization_failure")
            if case == "bind_failure":
                import socket
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0))
            if case == "test_failure":
                raise AssertionError("intentional_test_failure")
            result = sandbox.run(exercise(case, sandbox))
        assert not expected_failure
    except (RuntimeError, AssertionError, PermissionError):
        if not expected_failure:
            raise
        result = {"expected_failure": case}
    result.update(root=str(sandbox.root), cleaned=not sandbox.root.exists(),
                  writes=sorted(sandbox.writes))
    print(json.dumps(result))
    return 2 if expected_failure else 0


if __name__ == "__main__":
    raise SystemExit(child(sys.argv[1]))


import pytest  # noqa: E402 - child bootstrap must precede pytest/logging imports


@pytest.mark.parametrize("case", ["auth", "success", "input", "full_context", "failure", "output", "output_boundary", "cancel",
                                  "uncertain", "disconnect", "shutdown", "guards", "timeout",
                                  "init_failure", "enter_failure", "test_failure", "bind_failure"])
def test_offline_process(case):
    # No application imports in this pytest module; child clears inherited config
    # before importing anything from app. Only loader/temp variables are passed.
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "PATH", "TEMP", "TMP")
           if key in os.environ}
    result = subprocess.run([sys.executable, "-B", __file__, case], env=env,
                            capture_output=True, text=True, timeout=100, check=False)
    expected_failure = case in {"init_failure", "enter_failure", "test_failure", "bind_failure"}
    assert result.returncode == (2 if expected_failure else 0), result.stderr
    summary = json.loads(result.stdout)
    assert summary["cleaned"] and not Path(summary["root"]).exists()
    assert all(Path(summary["root"]) == Path(p) or Path(summary["root"]) in Path(p).parents
               for p in summary["writes"])
    assert "OFFLINE_FIXTURE_NOT_A_REAL_KEY" not in result.stdout + result.stderr
    assert "tf_session=" not in result.stdout + result.stderr
    if not expected_failure:
        assert "data\\user_data\\auth.json" in summary["files"] or "data/user_data/auth.json" in summary["files"]


def test_standalone_entrypoint():
    script = Path(__file__).resolve().parents[1] / "scripts/damon_offline.py"
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "PATH", "TEMP", "TMP")
           if key in os.environ}
    result = subprocess.run([sys.executable, "-B", str(script)], capture_output=True,
                            text=True, timeout=30, check=False, env=env)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["mode"] == "offline_asgi" and summary["attempts"] == 3
    assert summary["active_tasks"] == 0 and summary["cleaned"]
    refused = subprocess.run([sys.executable, "-B", str(script), "--listen"],
                             capture_output=True, text=True, timeout=10, check=False, env=env)
    assert refused.returncode != 0 and "ASGI only" in refused.stderr
