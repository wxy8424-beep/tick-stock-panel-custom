"""Damon text endpoints; metadata and errors never expose credentials."""
import asyncio
import hashlib
import json
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.services.damon_ai import profiles
from app.services.damon_ai.chat import ChatRequest, registry
from app.services.damon_ai.profiles import ChatError

router = APIRouter(prefix="/api/custom/damon/ai", tags=["damon-ai"])


@router.get("/status")
def status():
    return {"request_id": uuid4().hex, "phase": "1.2", "demo_only": False,
            "profile_ids": ["damon.mock"], "voice_modes": ["chained"],
            "real_voice_available": False, "production_tools": False, "text_chat_available": True}


def failure(code, status_code=400):
    return JSONResponse({"code": code, "request_id": uuid4().hex}, status_code=status_code)


def actor(request):
    # Existing app middleware remains authoritative. Also gate these cost-bearing
    # endpoints when mounted in isolation; bearer tokens have no Damon scope yet.
    from app.api import auth as auth_api
    from app.services import auth

    if request.headers.get("authorization"):
        raise ChatError("unauthorized")
    if auth.is_configured():
        token = request.cookies.get(auth_api.COOKIE_NAME, "")
        if not auth.is_valid_session(token):
            raise ChatError("unauthorized")
        return hashlib.sha256(token.encode()).hexdigest()
    if not auth_api._is_local_network(auth_api._client_ip(request)):
        raise ChatError("unauthorized")
    return "local-owner"


async def body(request):
    raw = bytearray()
    async with asyncio.timeout(5):
        async for chunk in request.stream():
            if len(raw) + len(chunk) > 64000:
                raise ChatError("input_limit")
            raw.extend(chunk)
    return json.loads(raw)


@router.get("/profiles")
async def model_profiles(request: Request):
    try:
        actor(request)
        return {"profiles": profiles.metadata()}
    except ChatError as exc:
        return failure(exc.code, 403 if exc.code == "unauthorized" else 400)
    except Exception:  # noqa: BLE001 - no configuration or exception text in response
        return failure("profile_configuration")


@router.post("/chat")
async def chat(request: Request):
    try:
        owner = actor(request)
        req = ChatRequest.model_validate(await body(request))
        if (sum(len(m.content) for m in req.messages) > 20000
                or any(m.role == "user" and len(m.content) > 8000 for m in req.messages)
                or any(not m.content.strip() for m in req.messages)
                or [m.role for m in req.messages] != [
                    "user" if i % 2 == 0 else "assistant" for i in range(len(req.messages))]
                or req.messages[-1].role != "user"):
            raise ChatError("input_limit")
        snapshot = profiles.resolve(req.profile_id)
        if (snapshot.context_window <= 0 or ai_input_tokens(req) + snapshot.max_tokens > snapshot.context_window):
            raise ChatError("input_limit")
        if any(snapshot.api_key in m.content for m in req.messages):
            raise ChatError("sensitive_input")
        turn = registry.admit(owner, req, snapshot)
    except ChatError as exc:
        return failure(exc.code, 403 if exc.code == "unauthorized" else 400)
    except Exception:  # noqa: BLE001 - reject validation input without FastAPI echoing it
        return failure("invalid_request")

    stream = registry.stream(turn, req, request.is_disconnected)
    first = await anext(stream)

    async def events():
        try:
            yield json.dumps(first, ensure_ascii=False) + "\n"
            async for event in stream:
                yield json.dumps(event, ensure_ascii=False) + "\n"
        finally:
            await registry.stop(turn)
            await stream.aclose()

    return StreamingResponse(events(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


def ai_input_tokens(req):
    from app.services.ai_provider import _estimate_input_tokens
    return _estimate_input_tokens([m.model_dump() for m in req.messages]) + 100


@router.post("/cancel")
async def cancel(request: Request):
    try:
        owner = actor(request)
        data = await body(request)
        if set(data) != {"conversation_id", "turn_id"} or not all(
                isinstance(v, str) and len(v) == 32 for v in data.values()):
            raise ChatError("invalid_request")
        turn = registry.cancel(owner, data["conversation_id"], data["turn_id"])
        cleanup = await registry.stop(turn)
        return {"request_id": turn.request_id, "status": "cancel_requested", "cleanup_state": cleanup}
    except ChatError as exc:
        return failure(exc.code, 403 if exc.code == "unauthorized" else 400)
    except Exception:  # noqa: BLE001
        return failure("invalid_request")
