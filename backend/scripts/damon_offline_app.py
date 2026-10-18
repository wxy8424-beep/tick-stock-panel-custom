"""Fake-only ASGI fixture, imported only after damon_offline.Sandbox bootstrap."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar


class FakeModel:
    """Trusted deterministic fixture; each Unicode point is one *fake* token unit."""

    def __init__(self, mode="success", text="OFFLINE_REPLY"):
        if mode not in {"success", "error", "hold", "uncooperative"}:
            raise ValueError("fake_mode_required")
        self.mode, self.text = mode, text
        self.started, self.release = asyncio.Event(), asyncio.Event()
        self.calls = []

    async def stream(self, messages, **kwargs):
        from app.services.damon_ai.profiles import ChatError

        # Check the actual adapter payload, including the production system message.
        if sum(len(message["content"]) for message in messages) > 3000:
            raise ChatError("input_limit")
        self.calls.append((messages, kwargs["max_tokens"]))
        self.started.set()
        if self.mode == "error":
            raise RuntimeError("FAKE_PRIVATE_ERROR")
        while self.mode in {"hold", "uncooperative"} and not self.release.is_set():
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                if self.mode != "uncooperative":
                    raise
        if len(self.text) > kwargs["max_tokens"]:
            raise ChatError("output_limit")
        for part in (self.text[:3], self.text[3:7], self.text[7:]):
            if part:
                yield part


class OfflineRuntime:
    def __init__(self, model=None):
        import os
        import sys
        from pathlib import Path

        from damon_offline import ACTIVE_SANDBOX

        if (ACTIVE_SANDBOX is None or "app.main" in sys.modules
                or Path(os.environ.get("DATA_DIR", "")) != ACTIVE_SANDBOX.root / "data"):
            raise RuntimeError("bootstrap_required")
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse

        from app.api import auth as auth_api
        from app.api import damon_ai
        from app.config import settings
        from app.extensions import (
            BACKEND_EXTENSION_API_VERSION,
            BackendExtensionRegistrar,
            BackendExtensionRegistry,
        )
        from app.services import ai_provider, auth
        from app.services.damon_ai.chat import ChatRegistry
        from app.services.damon_ai.profiles import ChatError

        self.model = FakeModel() if model is None else model
        if type(self.model) is not FakeModel:
            raise TypeError("only_builtin_fake_adapter_allowed")
        request_turns = ContextVar("offline_request_turns", default=None)

        class LimitedRegistry(ChatRegistry):
            attempts = 0
            halted = False

            def admit(self, actor, req, snapshot):
                if self.halted or self.attempts >= 3:
                    raise ChatError("offline_halted")
                if self.active:
                    raise ChatError("busy")
                if (len(req.messages[-1].content) > 1000
                        or sum(len(m.content) for m in req.messages) > 3000):
                    raise ChatError("input_limit")
                if snapshot.max_tokens > 512:
                    raise ChatError("output_limit")
                turn = super().admit(actor, req, snapshot)
                owned = request_turns.get()
                if owned is not None:
                    owned.append(turn)
                self.attempts += 1  # Reserve before await; failures/cancel never refund.
                return turn

            def cancel(self, *args):
                turn = super().cancel(*args)
                self.halted = True  # Conservative: every cancellation ends this test run.
                return turn

            async def stop(self, turn):
                state = await super().stop(turn)
                if state == "still_running" or turn.code != "completed":
                    self.halted = True
                return state

            def release(self, turn):
                if turn.code != "completed":
                    self.halted = True
                super().release(turn)

            async def stream(self, *args):
                source = super().stream(*args)
                try:
                    async for event in source:
                        # The existing registry can finish between its disconnect
                        # check and done check. Canonicalize this cancellation
                        # race only in the offline fixture, never to success.
                        if event["type"] == "error" and event.get("code") == "cancelled":
                            event = {**event, "type": "cancelled"}
                        yield event
                finally:
                    await source.aclose()

        self.registry = LimitedRegistry()  # Production 60s / 0.2s remain unchanged.
        self.password = "offline-fixture-password-only"
        self.auth = auth
        self.old_registry = damon_ai.registry
        self.old_stream = ai_provider.stream_snapshot_text
        self.old_factory = ai_provider._openai_client

        def no_sdk(*args, **kwargs):
            raise RuntimeError("real_sdk_forbidden")

        @asynccontextmanager
        async def lifespan(app):
            from app import secrets_store

            secrets_store.save({"ai_provider": "openai_compat", "ai_protocol": "chat_completions",
                                "ai_base_url": "https://offline.invalid/v1",
                                "ai_api_key": "OFFLINE_FIXTURE_NOT_A_REAL_KEY", "ai_model": "offline",
                                "ai_max_output_tokens": 512, "ai_context_window": 16384})
            auth.set_password(self.password)
            damon_ai.registry = self.registry
            ai_provider.stream_snapshot_text = self.model.stream
            ai_provider._openai_client = no_sdk
            try:
                yield
            finally:
                try:
                    self.registry.halted = True
                    self.model.release.set()
                    turns = list(self.registry.active.values())
                    for turn in turns:
                        await self.registry.stop(turn)
                    tasks = {t.task for t in turns if t.task is not None}
                    if tasks:
                        _, pending = await asyncio.wait(tasks, timeout=1)
                        if pending:
                            raise RuntimeError("offline_cleanup_incomplete")
                    await asyncio.sleep(0)
                finally:
                    damon_ai.registry = self.old_registry
                    ai_provider.stream_snapshot_text = self.old_stream
                    ai_provider._openai_client = self.old_factory

        self.app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
        registrar = BackendExtensionRegistrar("damon.offline", api_version=BACKEND_EXTENSION_API_VERSION)
        registrar.include_router(damon_ai.router)
        extensions = BackendExtensionRegistry()
        extensions.register(registrar)
        extensions.freeze()
        for router in registrar.routers:
            self.app.include_router(router)
        self.app.state.extension_registry = extensions
        self.app.include_router(auth_api.router)

        class DisconnectGuard:
            """Bind cleanup to this ASGI request, never to another busy request."""
            def __init__(self, app):
                self.app = app

            async def __call__(self, scope, receive, send):
                if scope["type"] != "http":
                    return await self.app(scope, receive, send)
                request = Request(scope)
                if (request.method, request.url.path) not in allowed:
                    response = JSONResponse({"code": "offline_route_denied"}, status_code=404)
                    return await response(scope, receive, send)
                if (request.url.path not in {"/api/auth/login", "/api/auth/status"}
                        and (request.headers.get("authorization") or not auth.is_configured()
                             or not auth.is_valid_session(request.cookies.get(auth_api.COOKIE_NAME, "")))):
                    response = JSONResponse({"code": "unauthorized"}, status_code=401)
                    return await response(scope, receive, send)
                owned = []
                token = request_turns.set(owned)
                disconnected = False

                async def observed_receive():
                    nonlocal disconnected
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        disconnected = True
                        for turn in owned:
                            if runtime.registry.active.get(turn.turn_id) is turn:
                                runtime.registry.cancel(turn.owner.actor, turn.conversation_id, turn.turn_id)
                    return message

                try:
                    await self.app(scope, observed_receive, send)
                except asyncio.CancelledError:
                    disconnected = True
                    raise
                finally:
                    if disconnected:
                        for turn in owned:
                            await runtime.registry.stop(turn)
                    request_turns.reset(token)

        runtime = self
        self.app.add_middleware(DisconnectGuard)
        allowed = {("GET", "/api/auth/status"), ("POST", "/api/auth/login"),
                   ("POST", "/api/auth/logout"), ("GET", "/api/custom/damon/ai/status"),
                   ("GET", "/api/custom/damon/ai/profiles"), ("POST", "/api/custom/damon/ai/chat"),
                   ("POST", "/api/custom/damon/ai/cancel")}

        assert settings.data_dir.is_absolute()

    def client(self):
        import httpx

        return httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, client=("127.0.0.1", 1)),
                                 base_url="http://127.0.0.1", trust_env=False)


def request(content="hello", conversation_id=None, messages=None):
    return {"profile_id": "damon.default", "conversation_id": conversation_id,
            "messages": messages or [{"role": "user", "content": content}]}


async def demo():
    import json

    runtime = OfflineRuntime()
    async with runtime.app.router.lifespan_context(runtime.app), runtime.client() as client:
        response = await client.post("/api/auth/login", json={"password": runtime.password})
        if response.status_code != 200:
            raise RuntimeError("offline_login_failed")
        for _ in range(3):
            response = await client.post("/api/custom/damon/ai/chat", json=request())
            if json.loads(response.text.splitlines()[-1])["type"] != "done":
                raise RuntimeError("offline_demo_failed")
    return {"mode": "offline_asgi", "attempts": runtime.registry.attempts,
            "active_tasks": len(runtime.registry.active)}
