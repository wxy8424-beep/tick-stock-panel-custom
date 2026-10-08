"""Damon's read-only HK dashboard, registered through the existing extension contract."""
from app.extensions import BACKEND_EXTENSION_API_VERSION, BackendExtensionRegistrar

EXTENSION_ID = "damon.hk-dashboard"
EXTENSION_API_VERSION = BACKEND_EXTENSION_API_VERSION


def setup(registrar: BackendExtensionRegistrar) -> None:
    from app.api.hk_dashboard import router

    registrar.include_router(router)
