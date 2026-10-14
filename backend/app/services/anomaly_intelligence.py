"""Read-only evidence aggregation. Never calculate indicators or fetch market data."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime

from app.services.anomaly_engine import AnomalyEvent, ArchiveInput
from app.services.evidence_execution import EvidenceExecutionResolver, TradingCalendarBindings
from app.services.evidence_policy import (
    EvidencePolicy,
    EvidencePolicyResolver,
    EvidencePolicyStore,
    PolicyModel,
)
from app.services.factor_snapshots import FactorSnapshotStore
from app.services.historical_baseline import HistoricalContextStore
from app.services.market_context import MarketContextStore

VERSION = "anomaly-intelligence-v1"
State = Literal["READY", "PARTIAL", "UNAVAILABLE", "BLOCKED"]


def instant(value) -> datetime:
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError("aware_time_required")
    return result


def finite(value, *, positive=False):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        return str(value) if number.is_finite() and (not positive or number > 0) else None
    except Exception:
        return None


class Evidence(PolicyModel):
    status: State
    blocker: str | None
    source_status: str | None
    source_blocker: str | None
    # Frozen canonical JSON preserves provenance and references without mutable dicts.
    fields_json: str
    provenance_json: str

    def to_dict(self):
        return {**json.loads(self.fields_json), "status": self.status, "blocker": self.blocker,
                "source_status": self.source_status, "source_blocker": self.source_blocker,
                "provenance": json.loads(self.provenance_json)}


def evidence(state="UNAVAILABLE", blocker="evidence_missing", raw=None, **fields):
    raw = raw or {}
    return Evidence(status=state, blocker=blocker, source_status=raw.get("status"),
                    source_blocker=raw.get("blocker"), fields_json=json.dumps(fields, allow_nan=False, sort_keys=True),
                    provenance_json=json.dumps(raw, allow_nan=False, sort_keys=True))


class AnomalyIntelligenceRecord(PolicyModel):
    intelligence_id: str
    event_id: str
    symbol: str
    market: Literal["CN", "HK", "US"]
    event_window_start: AwareDatetime
    event_window_end: AwareDatetime
    detected_at: AwareDatetime
    generated_at: AwareDatetime
    policy_id: str | None
    policy_version: str | None
    calendar_id: str | None
    calendar_version: str | None
    execution_json: str
    status: State
    blockers: tuple[str, ...]
    historical: Evidence
    market_evidence: Evidence
    factor: Evidence
    intelligence_version: Literal["anomaly-intelligence-v1"] = VERSION

    def to_dict(self):
        result = self.model_dump(mode="json", exclude={"historical", "market_evidence", "factor", "execution_json"})
        result.update(policy={"policy_id": self.policy_id, "version": self.policy_version},
                      execution=json.loads(self.execution_json), historical=self.historical.to_dict(),
                      market=self.market_evidence.to_dict(), factor=self.factor.to_dict(), version=self.intelligence_version)
        result["event_market"] = self.market
        return result


class AnomalyEvidenceCollector:
    def __init__(self, data_dir: Path, *, execution=None):
        self.policies = EvidencePolicyResolver(EvidencePolicyStore(data_dir))
        self.execution = execution or EvidenceExecutionResolver(TradingCalendarBindings())
        self.history = HistoricalContextStore(data_dir)
        self.markets = MarketContextStore(data_dir)
        self.factors = FactorSnapshotStore(data_dir)
        self.archive = ArchiveInput(data_dir)

    def _historical(self, event, policy):
        raw = self.history.read_many([event["event_id"]]).get(event["event_id"])
        if not raw:
            return evidence(blocker="historical_context_missing")
        fields = {key: raw.get(key) for key in ("atr14", "reference_close", "move_absolute", "move_atr_ratio",
            "source", "adjustment_method", "baseline_version", "as_of_date", "pit_capable")}
        fields.update(atr14=None, reference_close=None, move_atr_ratio=None)
        if finite(raw.get("atr14"), positive=True) is None:
            return evidence(blocker=raw.get("blocker") or "historical_values_unavailable", raw=raw, **fields)
        if not policy.allow_atr_display:
            return evidence(blocker="historical_display_not_permitted", raw=raw, **fields)
        day = instant(event["window_end"]).astimezone(ZoneInfo(
            self.execution.resolve(policy)["calendar_binding"]["timezone"])).date()
        if raw.get("symbol") != event["symbol"] or raw.get("market") != event["market"]:
            return evidence("BLOCKED", "historical_identity_conflict", raw, **fields)
        bars = raw.get("bars", [])
        end = raw.get("lookback_end") or raw.get("baseline_as_of")
        if (raw.get("as_of_date") != day.isoformat() or not end or date.fromisoformat(end) >= day or not bars
                or any(date.fromisoformat(row["date"]) >= day for row in bars)):
            return evidence("BLOCKED", "historical_completed_day_unverified", raw, **fields)
        fields["atr14"] = finite(raw.get("atr14"), positive=True)
        fields["reference_close"] = finite(raw.get("reference_close"), positive=True)
        if fields["atr14"] is None or fields["reference_close"] is None:
            return evidence(blocker=raw.get("blocker") or "historical_values_unavailable", raw=raw, **fields)
        scale_blockers = {"event_baseline_price_scale_unverified", "adjusted_baseline_realtime_price_basis_unverified"}
        scale_verified = raw.get("price_scale_verified") is True and raw.get("blocker") not in scale_blockers
        if policy.allow_move_atr_ratio and scale_verified:
            fields["move_atr_ratio"] = finite(raw.get("move_atr_ratio"))
        strict_pit = raw.get("pit_capable") is True
        if strict_pit:
            strict_pit = bool(raw.get("availability_evidence") and raw.get("source_vintage") and raw.get("input_available_at")
                              and instant(raw["input_available_at"]) <= instant(event["detected_at"]))
        blocker = raw.get("blocker") or (None if strict_pit else "source_vintage_unverified")
        if policy.allow_move_atr_ratio and not scale_verified:
            blocker = raw.get("blocker") or "event_baseline_price_scale_unverified"
        state = "READY" if strict_pit and raw.get("status") == "available" and blocker is None else "PARTIAL"
        return evidence(state, blocker, raw, **fields)

    def _market(self, event):
        raw = self.markets.read_many([event["event_id"]]).get(event["event_id"])
        if not raw:
            return evidence(blocker="market_context_missing")
        fields = {key: raw.get(key) for key in ("benchmark_symbol", "stock_change_pct", "benchmark_change_pct",
            "relative_move_pct", "context_class", "source", "context_version", "observations",
            "baseline_observation", "current_observation")}
        if raw.get("status") != "available":
            return evidence(blocker=raw.get("blocker") or "market_context_unavailable", raw=raw, **fields)
        if (raw.get("event_id") != event["event_id"] or raw.get("market") != event["market"]
                or (raw.get("symbol") is not None and raw["symbol"] != event["symbol"])
                or any(instant(raw[key]) != instant(event[key]) for key in ("window_start", "window_end"))):
            return evidence("BLOCKED", "market_event_window_conflict", raw, **fields)
        refs = [raw.get("stock_baseline"), raw.get("stock_current")]
        expected = [event["evidence"]["baseline"][0], event["evidence"]["current"]]
        if any(not ref or any(str(ref[key]) != str(original[key])
                             for key in ("snapshot_id", "price", "quote_timestamp", "receive_timestamp"))
               for ref, original in zip(refs, expected, strict=True)):
            return evidence("BLOCKED", "market_stock_reference_conflict", raw, **fields)
        ids = [ref["snapshot_id"] for ref in refs]
        rows = self.archive.read("SELECT id,symbol,market FROM market_snapshots WHERE id IN (?,?)", tuple(ids))
        if len(rows) != len(set(ids)) or any(row["symbol"] != event["symbol"] or row["market"] != event["market"] for row in rows):
            return evidence("BLOCKED", "market_stock_identity_unverified", raw, **fields)
        observations = raw.get("observations", [])
        if not observations:
            return evidence(blocker="market_observations_missing", raw=raw, **fields)
        if len(observations) > 1000:
            return evidence("BLOCKED", "market_observation_limit_exceeded", raw, **fields)
        ids = [row["snapshot_id"] for row in observations]
        quotes = self.archive.read("SELECT id,symbol,market,quote_timestamp,receive_timestamp FROM market_snapshots WHERE id IN ("
                                   + ",".join("?" for _ in ids) + ")", tuple(ids))
        indexed = {row["id"]: row for row in quotes}
        if any(row["snapshot_id"] not in indexed or indexed[row["snapshot_id"]]["symbol"] != raw["benchmark_symbol"]
               or indexed[row["snapshot_id"]]["market"] != event["market"]
               or Decimal(str(indexed[row["snapshot_id"]]["quote_timestamp"])) != Decimal(str(row["quote_timestamp"]))
               or indexed[row["snapshot_id"]]["receive_timestamp"] != row["receive_timestamp"] for row in observations):
            return evidence("BLOCKED", "market_benchmark_reference_conflict", raw, **fields)
        cutoff = instant(event["detected_at"]).timestamp() * 1000
        end = instant(event["window_end"]).timestamp() * 1000
        start = instant(event["window_start"]).timestamp() * 1000
        if any(row["quote_timestamp"] > end or row["receive_timestamp"] > cutoff
               or row["quote_timestamp"] > row["receive_timestamp"] or row["quote_timestamp"] < start - 30000
               for row in observations):
            return evidence("BLOCKED", "market_future_or_outside_window_observation", raw, **fields)
        if any(finite(fields[key]) is None for key in ("stock_change_pct", "benchmark_change_pct", "relative_move_pct")):
            return evidence(blocker="market_values_unavailable", raw=raw, **fields)
        return evidence("READY", None, raw, **fields)

    def _factor(self, event, policy, execution):
        calendar = execution["calendar_binding"]
        day = instant(event["window_end"]).astimezone(ZoneInfo(calendar["timezone"])).date()
        previous = self.execution.calendars.resolve_previous_trading_day(market=event["market"],
            calendar_id=calendar["calendar_id"], version=calendar["version"], date=day)
        if previous["status"] != "READY":
            return evidence("BLOCKED", previous["blocker"])
        snapshot_date = date.fromisoformat(previous["previous_trading_day"])
        result = self.factors.query(event["symbol"], snapshot_date=snapshot_date,
                                   definition_id=policy.definition_id, as_of_time=instant(event["detected_at"]))
        if result["status"] != "READY":
            return evidence(blocker=result.get("blocker", "factor_snapshot_unavailable"), raw=result)
        snapshot = result["snapshot"]
        fields = {key: snapshot.get(key) for key in ("snapshot_id", "definition_id", "universe_id", "total_score")}
        fields.update(factor_score=snapshot.get("total_score"), factor_version={item["registry_key"]: item["version"]
                      for item in execution["factor_identity_binding"]},
                      factor_binding=execution["factor_identity_binding"])
        if (snapshot["definition_id"] != policy.definition_id or snapshot["as_of_date"] != snapshot_date.isoformat()
                or snapshot["symbol"] != event["symbol"] or snapshot["market"] != event["market"]
                or snapshot["universe_id"] != policy.universe_id or event["symbol"] not in snapshot["universe_members"]):
            return evidence("BLOCKED", "factor_snapshot_identity_conflict", snapshot, **fields)
        cutoff = instant(event["detected_at"])
        if any(instant(snapshot[key]) > cutoff for key in ("available_at", "generated_at", "input_available_at")):
            return evidence("BLOCKED", "factor_snapshot_future", snapshot, **fields)
        metadata = snapshot["calculation_metadata"]["factors"]
        identities = execution["factor_identity_binding"]
        if (len(metadata) != len(identities) or {item["name"] for item in snapshot["factor_values"]}
                != {item["output_component"] for item in identities}):
            return evidence("BLOCKED", "factor_identity_binding_conflict", snapshot, **fields)
        for identity in identities:
            matches = [row for row in metadata if row["output_column"] == identity["output_component"]]
            if len(matches) != 1:
                return evidence("BLOCKED", "factor_identity_binding_conflict", snapshot, **fields)
            row = matches[0]
            if (row["registry"]["name"] != identity["registry_key"] or row["registry"]["version"] != identity["version"]
                    or row["period"] != identity["parameters"]["period"]):
                return evidence("BLOCKED", "factor_identity_binding_conflict", snapshot, **fields)
            norms = [item for item in snapshot["normalization"] if item["factor"] == identity["output_component"]]
            if (len(norms) != 1 or norms[0]["version"] != policy.normalization_version
                    or norms[0]["direction"] != row["direction"]):
                return evidence("BLOCKED", "factor_normalization_conflict", snapshot, **fields)
        return evidence("READY", None, snapshot, **fields)

    def collect(self, event: dict) -> AnomalyIntelligenceRecord:
        clean = AnomalyEvent.model_validate({key: event[key] for key in AnomalyEvent.model_fields}).model_dump(mode="json")
        resolved = self.policies.resolve(clean)
        if not instant(clean["window_start"]) < instant(clean["window_end"]) <= instant(clean["detected_at"]):
            resolved = {"status": "BLOCKED", "blocker": "event_window_time_conflict"}
        policy, execution = None, {}
        sections = {name: evidence(blocker="selection_not_resolved") for name in ("historical", "market", "factors")}
        blockers = []
        if resolved["status"] != "READY":
            blocker = resolved["blocker"]
            blockers.append("no_applicable_evidence_policy" if blocker == "no_matching_policy" else blocker)
            state = "BLOCKED"
        else:
            policy = EvidencePolicy.model_validate(resolved["selection_rules"])
            execution = self.execution.resolve(policy)
            if execution["status"] != "READY":
                blockers.append(execution["blocker"])
                state = "BLOCKED"
            else:
                selected = set(policy.required_evidence + policy.optional_evidence)
                calls = {"historical": lambda: self._historical(clean, policy),
                         "market": lambda: self._market(clean), "factors": lambda: self._factor(clean, policy, execution)}
                for name in selected:
                    try:
                        sections[name] = calls[name]()
                    except Exception:
                        sections[name] = evidence("BLOCKED", f"{name}_evidence_invalid_or_unreadable")
                    if sections[name].blocker:
                        blockers.append(f"{name}:{sections[name].blocker}")
                for name in sections.keys() - selected:
                    sections[name] = evidence(blocker="not_selected_by_policy")
                states = [sections[name].status for name in selected]
                if any(sections[name].status == "BLOCKED" for name in policy.required_evidence):
                    state = "BLOCKED"
                elif all(value == "READY" for value in states):
                    state = "READY"
                elif any(value in {"READY", "PARTIAL"} for value in states):
                    state = "PARTIAL"
                else:
                    state = "UNAVAILABLE"
        cal = execution.get("calendar_binding", {})
        return AnomalyIntelligenceRecord(intelligence_id=str(uuid4()), event_id=clean["event_id"],
            symbol=clean["symbol"], market=clean["market"], event_window_start=clean["window_start"],
            event_window_end=clean["window_end"], detected_at=clean["detected_at"], generated_at=datetime.now(UTC),
            policy_id=policy.policy_id if policy else None, policy_version=policy.version if policy else None,
            calendar_id=cal.get("calendar_id"), calendar_version=cal.get("version"),
            execution_json=json.dumps(execution, allow_nan=False, sort_keys=True), status=state,
            blockers=tuple(sorted(set(blockers))), historical=sections["historical"],
            market_evidence=sections["market"], factor=sections["factors"])


class AnomalyIntelligenceStore:
    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "user_data" / "anomaly_intelligence.sqlite3"

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=1)
        db.execute("CREATE TABLE IF NOT EXISTS intelligence (event_id TEXT PRIMARY KEY, generated_at TEXT NOT NULL, payload TEXT NOT NULL)")
        db.execute("CREATE INDEX IF NOT EXISTS intelligence_recent ON intelligence(generated_at DESC,event_id)")
        db.execute("CREATE TABLE IF NOT EXISTS consumer_cursor (singleton INTEGER PRIMARY KEY, sequence INTEGER NOT NULL, event_id TEXT)")
        return db

    def save(self, record: AnomalyIntelligenceRecord, *, sequence=None) -> dict:
        record = AnomalyIntelligenceRecord.model_validate_json(record.model_dump_json())
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT payload FROM intelligence WHERE event_id=?", (record.event_id,)).fetchone()
            if old:
                left, right = json.loads(old[0]), json.loads(record.model_dump_json())
                for key in ("generated_at", "intelligence_id"):
                    left.pop(key)
                    right.pop(key)
                if left != right:
                    return {"status": "BLOCKED", "blocker": "intelligence_identity_conflict"}
            else:
                db.execute("INSERT INTO intelligence VALUES (?,?,?)",
                           (record.event_id, record.generated_at.isoformat(), record.model_dump_json()))
            if sequence is not None:
                db.execute("INSERT OR REPLACE INTO consumer_cursor VALUES (1,?,?)", (sequence, record.event_id))
        return {"status": "SAVED", "blocker": None}

    def get(self, event_id: str) -> AnomalyIntelligenceRecord | None:
        if not self.path.exists():
            return None
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
            row = db.execute("SELECT payload FROM intelligence WHERE event_id=?", (event_id,)).fetchone()
        return AnomalyIntelligenceRecord.model_validate_json(row[0]) if row else None

    def list_recent(self, limit=100):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("bounded_recent_query_required")
        if not self.path.exists():
            return ()
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
            rows = db.execute("SELECT payload FROM intelligence ORDER BY generated_at DESC,event_id LIMIT ?", (limit,)).fetchall()
        return tuple(AnomalyIntelligenceRecord.model_validate_json(row[0]) for row in rows)


def read_event(data_dir: Path, event_id: str):
    path = Path(data_dir) / "user_data" / "anomaly_engine.sqlite3"
    if not path.exists():
        return None
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='anomaly_events'").fetchone():
            return None
        row = db.execute("SELECT payload FROM anomaly_events WHERE event_id=?", (event_id,)).fetchone()
    return json.loads(row[0]) if row else None
