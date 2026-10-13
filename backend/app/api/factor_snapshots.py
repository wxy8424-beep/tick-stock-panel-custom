"""Read-only frozen factor evidence, no calculation or provider requests."""
from datetime import date

from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime

from app.market_session import market_from_symbol
from app.services.factor_snapshots import FactorSnapshotStore

router = APIRouter(prefix="/api/factor-snapshots", tags=["factor-snapshots"])


@router.get("/{symbol}")
def factor_snapshot(request: Request, symbol: str, as_of_time: AwareDatetime,
                    snapshot_date: date, definition_id: str = Query(..., min_length=1, max_length=128)):
    if market_from_symbol(symbol) is None or len(symbol) > 128:
        return {"status": "UNAVAILABLE", "blocker": "symbol_market_unknown"}
    repo = getattr(request.app.state, "repo", None)
    data_dir = getattr(getattr(repo, "store", None), "data_dir", None)
    if data_dir is None:
        return {"status": "UNAVAILABLE", "blocker": "snapshot_storage_not_initialized"}
    try:
        return FactorSnapshotStore(data_dir).query(symbol, snapshot_date=snapshot_date,
            definition_id=definition_id, as_of_time=as_of_time)
    except Exception:
        return {"status": "UNAVAILABLE", "blocker": "snapshot_storage_or_evidence_unavailable"}
