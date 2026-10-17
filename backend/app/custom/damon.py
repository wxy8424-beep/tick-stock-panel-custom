"""Damon's read-only HK dashboard, registered through the existing extension contract."""
from app.extensions import BACKEND_EXTENSION_API_VERSION, BackendExtensionRegistrar

EXTENSION_ID = "damon.hk-dashboard"
EXTENSION_API_VERSION = BACKEND_EXTENSION_API_VERSION


def setup(registrar: BackendExtensionRegistrar) -> None:
    from app.api.anomalies import router as anomaly_router
    from app.api.anomaly_intelligence import router as intelligence_router
    from app.api.damon_ai import router as damon_ai_router
    from app.api.factor_snapshots import router as factor_snapshots_router
    from app.api.hk_dashboard import router
    from app.api.us_dashboard import router as us_router

    registrar.include_router(router)
    registrar.include_router(us_router)
    registrar.include_router(anomaly_router)
    registrar.include_router(factor_snapshots_router)
    registrar.include_router(intelligence_router)
    registrar.include_router(damon_ai_router)
