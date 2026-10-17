"""Static Phase 1 capabilities; never read model configuration or credentials."""
from uuid import uuid4

from fastapi import APIRouter

router = APIRouter(prefix="/api/custom/damon/ai", tags=["damon-ai"])


@router.get("/status")
def status():
    return {"request_id": uuid4().hex, "phase": 1, "demo_only": True,
            "profile_ids": ["damon.mock"], "voice_modes": ["chained"],
            "real_voice_available": False, "production_tools": False}
