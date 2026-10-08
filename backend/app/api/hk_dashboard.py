"""Read-only HK aggregation. SDK work lives in the service, not HTTP handlers."""
from fastapi import APIRouter, HTTPException, Request

from app.services.hk_dashboard_service import HKDashboardService, validate_symbol

router = APIRouter(prefix="/api/dashboard", tags=["hk-dashboard"])
service = HKDashboardService()


@router.get("/hk")
def hk_dashboard(request: Request, symbol: str | None = None):
    try:
        if symbol is not None:
            validate_symbol(symbol)
    except ValueError:
        raise HTTPException(status_code=422, detail="焦点股票必须是数字代码.HK") from None
    qs = getattr(request.app.state, "quote_service", None)
    snapshots = qs.get_non_cn_quotes() if qs else []
    return service.get(symbol, snapshots)
