"""US-only read aggregation; no CN datasets or trading routes."""
from contextlib import asynccontextmanager

from fastapi import APIRouter, HTTPException, Request

from app.services.us_dashboard_service import USDashboardService, validate_symbol

service = USDashboardService(universe_enabled=True)


@asynccontextmanager
async def lifespan(app):
    yield
    service.close()


router = APIRouter(prefix="/api/dashboard", tags=["us-dashboard"], lifespan=lifespan)


@router.get("/us")
def us_dashboard(request: Request, symbol: str | None = None):
    try:
        if symbol is not None:
            validate_symbol(symbol)
    except ValueError:
        raise HTTPException(status_code=422, detail="焦点股票必须使用美股标准代码 (如 AAPL.US)") from None
    qs = getattr(request.app.state, "quote_service", None)
    return service.get(symbol, qs.get_non_cn_quotes() if qs else [])
