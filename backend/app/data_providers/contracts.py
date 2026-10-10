"""Optional market and quantity contracts; absent metadata retains legacy behavior."""
from __future__ import annotations

MARKETS = ("CN", "HK", "US")
METADATA_COLUMNS = ("market", "timezone", "currency", "volume_unit", "quantity_unit")
CAPABILITY_STATUSES = {
    "supported", "unsupported", "contract_blocked", "entitlement_denied", "unavailable", "empty",
}
QUANTITY_UNITS = {"legacy_100_shares", "shares", "board_lots", "contracts", "unknown"}


def dataset_status(provider, dataset: str, market: str | None = None) -> dict:
    declared = dataset in provider.config.datasets
    metadata = getattr(provider, "market_capabilities", None)
    if market is not None and market not in MARKETS:
        return {"status": "unsupported", "reason": "unknown_market"}
    if metadata is None:
        return {"status": "supported" if declared else "unsupported", "reason": None}
    entries = metadata.get(dataset, {})
    if market is not None:
        entry = dict(entries.get(market) or {"status": "unsupported", "reason": "market_not_declared"})
        if entry.get("status") not in CAPABILITY_STATUSES:
            return {"status": "contract_blocked", "reason": "invalid_capability_status"}
        if entry["status"] == "supported" and not declared:
            return {"status": "contract_blocked", "reason": "dataset_not_declared"}
        return entry
    statuses = [dataset_status(provider, dataset, item) for item in MARKETS]
    if all(item["status"] == "supported" for item in statuses):
        return {"status": "supported", "reason": None}
    if any(item["status"] == "supported" for item in statuses):
        return {"status": "contract_blocked", "reason": "market_required"}
    return next((item for item in statuses if item["status"] == "contract_blocked"), statuses[0])


def validate_quantity_units(data) -> None:
    """Reject explicit unknown/incompatible units before legacy CN consumption. No conversion."""
    if isinstance(data, dict):
        values = [data[key] for key in ("volume_unit", "quantity_unit") if key in data]
    else:
        values = [
            value for key in ("volume_unit", "quantity_unit") if key in data.columns
            for value in data[key].unique().to_list()
        ]
    for value in values:
        if value is None or value == "unknown" or value not in QUANTITY_UNITS:
            raise ValueError("quantity_unit_unknown")
        if value != "legacy_100_shares":
            raise ValueError("quantity_unit_incompatible")
