"""Read-only anomaly/evidence queries. Never evaluate or fetch quotes on GET."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import AwareDatetime

from app.services.anomaly_engine import AnomalyStore

router = APIRouter(prefix="/api/intraday/anomalies", tags=["anomalies"])


def _store(request):
    repo = getattr(request.app.state, "repo", None)
    data_dir = getattr(getattr(repo, "store", None), "data_dir", None)
    return AnomalyStore(data_dir) if data_dir is not None else None


@router.get("/recent")
def recent(request: Request, symbol: str | None = Query(None, max_length=128),
           market: Literal["CN", "HK", "US"] | None = None,
           event_type: Literal["rapid_price_move", "intraday_breakout", "volatility_expansion"] | None = None,
           severity: Literal["low", "medium", "high"] | None = None,
           start: AwareDatetime | None = None, end: AwareDatetime | None = None,
           before_id: int | None = Query(None, ge=1), limit: int = Query(100, ge=1, le=200)):
    store = _store(request)
    try:
        return store.query(symbol=symbol, market=market, event_type=event_type, severity=severity,
                           start_ms=int(start.timestamp() * 1000) if start else None,
                           end_ms=int(end.timestamp() * 1000) if end else None,
                           before_id=before_id, limit=limit) if store else {"rows": [], "next_before_id": None}
    except ValueError:
        raise HTTPException(422, "无效的异动查询范围") from None
    except Exception:
        raise HTTPException(503, "异动事件存储暂不可读") from None


@router.get("/episodes")
def episodes(request: Request, symbol: str = Query(..., max_length=128), limit: int = Query(100, ge=1, le=200)):
    store = _store(request)
    try:
        return {"rows": store.episodes(symbol, limit) if store else []}
    except Exception:
        raise HTTPException(503, "异动 episode 暂不可读") from None


@router.get("/health")
def health(request: Request):
    worker = getattr(request.app.state, "anomaly_worker", None)
    return worker.health() if worker else {"state": "not_started", "diagnostics": [],
        "volatility_expansion": {"status": "unsupported", "reason": "snapshot_cadence_not_authoritative"},
        "volume_spike": {"status": "unsupported", "reason": "longbridge_volume_unit_unverified"}}
