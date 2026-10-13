"""Read-only anomaly/evidence queries. Never evaluate or fetch quotes on GET."""
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import AwareDatetime

from app.market_session import get_market_session
from app.services.anomaly_engine import AnomalyStore, StaleAnomalyCursorError
from app.services.historical_baseline import (
    HistoricalContextStore,
    enrich_response,
    unknown_context,
)
from app.services.market_context import (
    MarketContextStore,
    enrich_market_response,
    unknown_market_context,
)

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
        page = store.query(symbol=symbol, market=market, event_type=event_type, severity=severity,
                           start_ms=int(start.timestamp() * 1000) if start else None,
                           end_ms=int(end.timestamp() * 1000) if end else None,
                           before_id=before_id, limit=limit) if store else {"rows": [], "next_before_id": None}
        return enrich_market_response(store.path.parent.parent, enrich_response(store.path.parent.parent, page)) if store else page
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


@router.get("/incremental")
def incremental(request: Request, after_id: int = Query(0, ge=0),
                after_event_id: str | None = Query(None, max_length=64), limit: int = Query(100, ge=1, le=200)):
    store = _store(request)
    if store is None:
        raise HTTPException(503, "异动事件存储未初始化")
    try:
        return enrich_market_response(store.path.parent.parent, enrich_response(store.path.parent.parent, store.incremental(after_id, after_event_id, limit)))
    except StaleAnomalyCursorError:
        raise HTTPException(409, "交付游标失效. 请刷新后重新读取历史. 不会自动跳过事件") from None
    except ValueError:
        raise HTTPException(422, "无效的交付游标") from None
    except Exception:
        raise HTTPException(503, "异动事件存储暂不可读") from None


@router.get("/historical-context")
def historical_context(request: Request, event_id: str = Query(..., min_length=1, max_length=64)):
    store = _store(request)
    if store is None:
        return unknown_context("event_storage_unavailable")
    try:
        return HistoricalContextStore(store.path.parent.parent).read_many([event_id]).get(event_id, unknown_context())
    except Exception:
        return unknown_context("context_storage_unavailable")


@router.get("/historical-contexts")
def historical_contexts(request: Request, event_id: Annotated[list[str], Query(min_length=1, max_length=100)]):
    if any(not value or len(value) > 64 for value in event_id):
        raise HTTPException(422, "无效事件ID")
    store = _store(request)
    try:
        values = HistoricalContextStore(store.path.parent.parent).read_many(event_id) if store else {}
        return {"contexts": {key: values.get(key, unknown_context()) for key in event_id}}
    except Exception:
        return {"contexts": {key: unknown_context("context_storage_unavailable") for key in event_id}}


@router.get("/health")
def health(request: Request):
    worker = getattr(request.app.state, "anomaly_worker", None)
    result = worker.health() if worker else {"state": "not_started", "diagnostics": [],
        "volatility_expansion": {"status": "unsupported", "reason": "snapshot_cadence_not_authoritative"},
        "volume_spike": {"status": "unsupported", "reason": "longbridge_volume_unit_unverified"}}
    now = datetime.now(UTC)
    result["observed_at"] = now.isoformat()
    result["market_sessions"] = {
        market: {"session_state": session.session_state, "diagnostic_code": session.diagnostic_code}
        for market in ("CN", "HK", "US")
        for session in (get_market_session(market, now),)
    }
    store = _store(request)
    try:
        result["delivery"] = {"state": "available", **store.delivery_state()} if store else {"state": "unknown"}
    except Exception:
        result["delivery"] = {"state": "unavailable"}
    return result


@router.get("/market-contexts")
def market_contexts(request: Request, event_id: Annotated[list[str], Query(min_length=1, max_length=100)]):
    if any(not value or len(value) > 64 for value in event_id):
        raise HTTPException(422, "无效事件ID")
    store = _store(request)
    try:
        values = MarketContextStore(store.path.parent.parent).read_many(event_id) if store else {}
        return {"contexts": {key: values.get(key, unknown_market_context({"event_id": key})) for key in event_id}}
    except Exception:
        return {"contexts": {key: unknown_market_context({"event_id": key}, "market_context_storage_unavailable") for key in event_id}}
