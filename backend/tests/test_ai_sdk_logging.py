"""Installed SDK requests over MockTransport only; no real secrets or sockets."""
import asyncio
import json
import logging
import socket
import sqlite3
import subprocess

import httpx
import openai
import pytest

from app.services import ai_provider
from app.services.ai_sdk_logging import _FILTER, _LOGGERS

FAKE_KEY = "FAKE_LOG_TEST_CREDENTIAL_NEVER_REAL"
URL_MARKER = "sensitive-log-test-path"
REQUEST_BODY = "PRIVATE_REQUEST_BODY_MARKER"
RESPONSE_BODY = "PRIVATE_RESPONSE_BODY_MARKER"


@pytest.mark.parametrize("level", [logging.INFO, logging.DEBUG])
@pytest.mark.parametrize("protocol", ["chat_completions", "responses"])
@pytest.mark.parametrize("upstream_error", [False, True])
async def test_installed_sdk_logs_are_suppressed_over_offline_transport(
        level, protocol, upstream_error, monkeypatch, caplog):
    def forbidden(*args, **kwargs):
        raise AssertionError("network, secrets and production storage forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(asyncio.BaseEventLoop, "create_connection", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(ai_provider.secrets_store, "load", forbidden)
    requests = []

    async def respond(request):
        requests.append(request)
        assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
        assert URL_MARKER in str(request.url)
        assert REQUEST_BODY in request.content.decode()
        if upstream_error:
            return httpx.Response(400, json={"error": {"message": RESPONSE_BODY + FAKE_KEY}})
        if protocol == "responses":
            events = [
                {"type": "response.output_text.delta", "delta": RESPONSE_BODY},
                {"type": "response.completed", "response": {"status": "completed"}},
            ]
        else:
            events = [
                {"choices": [{"index": 0, "delta": {"content": RESPONSE_BODY}, "finish_reason": None}]},
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            ]
        return httpx.Response(200, headers={"Content-Type": "text/event-stream",
                                           "x-private-response": RESPONSE_BODY},
                              content="".join(f"data: {json.dumps(e)}\n\n" for e in events))

    real_client = httpx.AsyncClient

    class OfflineClient(real_client):
        def __init__(self, **kwargs):
            super().__init__(**kwargs, transport=httpx.MockTransport(respond), trust_env=False)

    monkeypatch.setattr(httpx, "AsyncClient", OfflineClient)
    attempted_records = []
    real_filter = _FILTER.filter

    def observe_filter(record):
        attempted_records.append((record.name, record.levelno))
        return real_filter(record)

    monkeypatch.setattr(_FILTER, "filter", observe_filter)
    caplog.set_level(level)
    # Exercise SDK-specific levels too: OPENAI_LOG=debug can override the root level.
    for name in ("openai", "openai._base_client", "httpx", "httpcore.http11"):
        caplog.set_level(level, logger=name)
    logging.getLogger("app.damon_log_test").info("business log remains available")
    deltas = []
    try:
        async for text in ai_provider.stream_snapshot_text(
                [{"role": "user", "content": REQUEST_BODY}], api_key=FAKE_KEY,
                base_url=f"https://offline.invalid/{URL_MARKER}/v1", model="offline-model",
                protocol=protocol, user_agent="offline-test", max_tokens=20, timeout=1):
            deltas.append(text)
    except openai.BadRequestError:
        assert upstream_error
    else:
        assert not upstream_error
        assert "".join(deltas) == RESPONSE_BODY
    assert len(requests) == 1
    for secret in (FAKE_KEY, f"Bearer {FAKE_KEY}", URL_MARKER, REQUEST_BODY, RESPONSE_BODY):
        assert secret not in caplog.text
    assert "business log remains available" in caplog.text
    assert not any(r.name.startswith(("openai", "httpx", "httpcore")) for r in caplog.records)
    assert ("httpx", logging.INFO) in attempted_records
    if level == logging.DEBUG:
        assert ("openai._base_client", logging.DEBUG) in attempted_records


def test_concrete_sdk_loggers_block_critical_records_and_httpcore_trace(caplog):
    from httpcore._trace import Trace

    caplog.set_level(logging.DEBUG)
    for name in _LOGGERS:
        logger = logging.getLogger(name)
        caplog.set_level(logging.DEBUG, logger=name)
        logger.critical("Authorization: Bearer %s %s %s", FAKE_KEY, URL_MARKER, RESPONSE_BODY)
    # MockTransport bypasses httpcore I/O. Exercise its actual Trace formatter
    # separately, including the response-header and exception diagnostic paths.
    with Trace("receive_response_headers", logging.getLogger("httpcore.http11"),
               kwargs={"request": REQUEST_BODY, "authorization": FAKE_KEY}) as trace:
        trace.return_value = [(b"x-private-response", RESPONSE_BODY.encode())]
    with pytest.raises(RuntimeError), Trace("connect_tcp", logging.getLogger("httpcore.connection")):
        raise RuntimeError(FAKE_KEY + URL_MARKER)
    assert not caplog.records
