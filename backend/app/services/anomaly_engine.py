"""Versioned archived-price observations with transactional, durable episodes."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.market_session import get_market_session, market_from_symbol
from app.services.snapshot_archive import SnapshotArchive

EventType = Literal["rapid_price_move", "intraday_breakout", "volatility_expansion"]
Severity = Literal["low", "medium", "high"]
SEVERITIES = {"low": 1, "medium": 2, "high": 3}
PRICE_ONLY_UNKNOWN = {"volume_unknown", "volume_unit_unknown", "prev_close_unknown",
                      "open_unknown", "high_unknown", "low_unknown"}


class Rule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rule_id: str = Field(pattern=r"^[a-z0-9_]{1,64}$")
    event_type: EventType
    window_seconds: int = Field(ge=60, le=900, strict=True)
    threshold: Decimal = Field(gt=0, le=1)


DEFAULT_RULES = (
    Rule(rule_id="rapid_move_1m", event_type="rapid_price_move", window_seconds=60, threshold="0.01"),
    Rule(rule_id="rapid_move_5m", event_type="rapid_price_move", window_seconds=300, threshold="0.02"),
    Rule(rule_id="rapid_move_15m", event_type="rapid_price_move", window_seconds=900, threshold="0.04"),
    Rule(rule_id="intraday_breakout", event_type="intraday_breakout", window_seconds=900, threshold="0.005"),
)


class AnomalyPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rules: tuple[Rule, ...] = Field(default=DEFAULT_RULES, min_length=1, max_length=10)
    medium_multiple: Decimal = Field(default=Decimal("1.5"), gt=1)
    high_multiple: Decimal = Field(default=Decimal("2"), gt=1)
    boundary_tolerance_ms: int = Field(default=30000, ge=0, le=120000, strict=True)
    max_gap_ms: int = Field(default=120000, ge=1000, le=120000, strict=True)
    cooldown_ms: int = Field(default=120000, ge=0, le=3600000, strict=True)
    episode_expiry_ms: int = Field(default=180000, ge=1000, le=3600000, strict=True)
    min_breakout_samples: int = Field(default=3, ge=2, le=100, strict=True)

    @model_validator(mode="after")
    def consistent(self):
        if self.high_multiple <= self.medium_multiple or len({rule.rule_id for rule in self.rules}) != len(self.rules):
            raise ValueError("ordered severity multiples and unique rule IDs required")
        return self

    @property
    def version(self) -> str:
        # Any threshold/gate/cooldown change creates a new episode namespace.
        return "1-" + hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:16]


class SnapshotRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    snapshot_id: int
    price: Decimal
    quote_timestamp: int
    receive_timestamp: int
    quality_state: Literal["valid", "unknown"]
    warning_codes: tuple[str, ...]


class EventEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    current: SnapshotRef
    baseline: tuple[SnapshotRef, ...]
    sample_count: int
    maximum_gap_ms: int
    baseline_scope: Literal["timestamp_boundary", "prior_archived_intraday_prices"]
    volume_used: Literal[False] = False
    volume_status: Literal["unsupported_unit_unverified"] = "unsupported_unit_unverified"
    history_truncated: bool
    medium_multiple: Decimal
    high_multiple: Decimal
    trigger_multiple: Decimal


class AnomalyEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    event_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    episode_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    symbol: str = Field(max_length=128)
    market: Literal["CN", "HK", "US"]
    event_type: EventType
    direction: Literal["up", "down"]
    severity: Severity
    status: Literal["first_trigger", "sustained", "escalation"]
    detected_at: AwareDatetime
    window_start: AwareDatetime
    window_end: AwareDatetime
    observed_value: Decimal
    baseline_value: Decimal
    change_value: Decimal
    change_pct: Decimal  # Fraction, never percentage points.
    threshold: Decimal
    evidence: EventEvidence
    rule_id: str
    rule_version: str
    source: Literal["longbridge_snapshot_archive"] = "longbridge_snapshot_archive"


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _number(value) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError("snapshot_numeric_unknown")
    result = Decimal(str(value))
    if not result.is_finite() or result <= 0 or not -128 <= result.adjusted() <= 128:
        raise ValueError("snapshot_numeric_unknown")
    return result


def _milliseconds(value) -> int:
    number = _number(value)
    if number != number.to_integral_value() or number > 253402300799999:
        raise ValueError("snapshot_timestamp_unknown")
    return int(number)


def _time(milliseconds: int) -> datetime:
    return datetime.fromtimestamp(milliseconds / 1000, UTC)


class ArchiveInput:
    """Read the existing archive schema only; no SDK, new quote cache or writes."""

    def __init__(self, data_dir: Path):
        self.path = SnapshotArchive(data_dir).path

    def read(self, sql: str, params=()) -> list[dict]:
        if not self.path.exists():
            return []
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
            db.row_factory = sqlite3.Row
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='market_snapshots'").fetchone():
                return []
            return [dict(row) for row in db.execute(sql, params)]

    def latest_id(self) -> int:
        rows = self.read("SELECT MAX(id) AS last_id FROM market_snapshots")
        return (rows[0]["last_id"] or 0) if rows else 0

    def page(self, after_id: int, limit: int) -> list[dict]:
        return self.read("SELECT * FROM market_snapshots WHERE id>? ORDER BY id LIMIT ?", (after_id, limit))

    def history(self, current: dict, as_of_ms: int, midnight_ms: int) -> tuple[list[dict], bool]:
        rows = self.read("""SELECT * FROM market_snapshots WHERE symbol=? AND market=? AND id<?
            AND receive_timestamp>=? AND receive_timestamp<=? ORDER BY id DESC LIMIT 1001""",
                         (current["symbol"], current["market"], current["id"], midnight_ms, as_of_ms))
        return list(reversed(rows[:1000])), len(rows) > 1000


class StaleAnomalyCursorError(ValueError):
    """Cursor anchor no longer exists or belongs to a different archive."""


class AnomalyStore:
    """Events, episodes and consumer cursor commit together in independent SQLite."""

    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "user_data" / "anomaly_engine.sqlite3"

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=1)
        db.execute("CREATE TABLE IF NOT EXISTS anomaly_events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL, episode_id TEXT NOT NULL, symbol TEXT NOT NULL, market TEXT NOT NULL, event_type TEXT NOT NULL, severity TEXT NOT NULL, detected_at INTEGER NOT NULL, payload TEXT NOT NULL)")
        db.execute("CREATE INDEX IF NOT EXISTS anomaly_events_time ON anomaly_events(detected_at DESC,id DESC)")
        db.execute("CREATE TABLE IF NOT EXISTS anomaly_episodes (episode_key TEXT PRIMARY KEY, symbol TEXT NOT NULL, market TEXT NOT NULL, payload TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS anomaly_cursors (ruleset TEXT PRIMARY KEY, last_id INTEGER NOT NULL)")
        return db

    def query(self, *, symbol=None, market=None, event_type=None, severity=None,
              start_ms=None, end_ms=None, before_id=None, limit=100) -> dict:
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        if ((market is not None and market not in {"CN", "HK", "US"})
                or (event_type is not None and event_type not in {"rapid_price_move", "intraday_breakout", "volatility_expansion"})
                or (severity is not None and severity not in SEVERITIES)):
            raise ValueError("unknown anomaly filter")
        for value in (start_ms, end_ms, before_id):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("nonnegative integer cursor/times required")
        if start_ms is not None and end_ms is not None and start_ms > end_ms:
            raise ValueError("ordered time range required")
        if not self.path.exists():
            return {"rows": [], "next_before_id": None}
        filters, params = [], []
        for field, value, operator in (("symbol", symbol, "="), ("market", market, "="),
                                       ("event_type", event_type, "="), ("severity", severity, "="),
                                       ("detected_at", start_ms, ">="), ("detected_at", end_ms, "<="), ("id", before_id, "<")):
            if value is not None:
                filters.append(f"{field}{operator}?")
                params.append(value)
        where = " WHERE " + " AND ".join(filters) if filters else ""
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='anomaly_events'").fetchone():
                return {"rows": [], "next_before_id": None}
            rows = db.execute("SELECT id,payload FROM anomaly_events" + where + " ORDER BY id DESC LIMIT ?", [*params, limit + 1]).fetchall()
        selected = rows[:limit]
        events = [{"store_id": row[0], **json.loads(row[1])} for row in selected]
        return {"rows": events, "next_before_id": selected[-1][0] if len(rows) > limit else None,
                "resume_cursor": {"sequence": events[0]["store_id"], "event_id": events[0]["event_id"]} if events else {"sequence": 0, "event_id": None}}

    def incremental(self, after_id: int, after_event_id: str | None, limit=100) -> dict:
        if type(after_id) is not int or after_id < 0 or type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("bounded positive sequence/limit required")
        if bool(after_event_id) != bool(after_id):
            raise ValueError("positive cursor requires event anchor")
        empty = {"rows": [], "next_cursor": {"sequence": 0, "event_id": None}, "has_more": False,
                 "latest_sequence": 0, "latest_event_detected_at": None}
        if not self.path.exists():
            if after_id:
                raise StaleAnomalyCursorError("cursor_anchor_missing")
            return empty
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
            db.execute("BEGIN")  # One consistent view during concurrent event inserts.
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='anomaly_events'").fetchone():
                if after_id:
                    raise StaleAnomalyCursorError("cursor_anchor_missing")
                return empty
            if after_id:
                anchor = db.execute("SELECT event_id FROM anomaly_events WHERE id=?", (after_id,)).fetchone()
                if not anchor or anchor[0] != after_event_id:
                    raise StaleAnomalyCursorError("cursor_anchor_missing_or_changed")
            latest = db.execute("SELECT MAX(id),MAX(detected_at) FROM anomaly_events").fetchone()
            rows = db.execute("SELECT id,payload FROM anomaly_events WHERE id>? ORDER BY id ASC LIMIT ?", (after_id, limit + 1)).fetchall()
        selected = rows[:limit]
        events = [{"store_id": row[0], **json.loads(row[1])} for row in selected]
        return {"rows": events,
                "next_cursor": {"sequence": events[-1]["store_id"], "event_id": events[-1]["event_id"]} if events else {"sequence": after_id, "event_id": after_event_id},
                "has_more": len(rows) > limit,
                "latest_sequence": latest[0] or 0,
                "latest_event_detected_at": _time(latest[1]).isoformat() if latest[1] is not None else None}

    def delivery_state(self) -> dict:
        # No cursor validation is needed for a zero-position metadata read.
        page = self.incremental(0, None, limit=1)
        return {"latest_sequence": page["latest_sequence"], "latest_event_detected_at": page["latest_event_detected_at"]}

    def episodes(self, symbol: str, limit=100) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("bounded episode limit required")
        if not self.path.exists():
            return []
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='anomaly_episodes'").fetchone():
                return []
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM anomaly_episodes WHERE symbol=? ORDER BY rowid DESC LIMIT ?", (symbol, limit))]


class AnomalyEngine:
    def __init__(self, data_dir: Path, policy: AnomalyPolicy | None = None):
        self.input, self.store = ArchiveInput(data_dir), AnomalyStore(data_dir)
        self.policy = policy or AnomalyPolicy()

    def _ref(self, row, market, as_of_ms):
        if row["provider"] != "longbridge" or row["market"] != market or market_from_symbol(row["symbol"]) != market:
            raise ValueError("snapshot_identity_conflict")
        price, quote, receive = _number(row["price"]), _milliseconds(row["quote_timestamp"]), _milliseconds(row["receive_timestamp"])
        raw_warnings = row.get("warnings")
        if isinstance(raw_warnings, str):
            warnings = json.loads(raw_warnings)
        elif isinstance(raw_warnings, list):
            warnings = raw_warnings
        else:
            raise ValueError("price_quality_unknown")
        if (not isinstance(warnings, list) or any(not isinstance(code, str) for code in warnings)
                or row["quality_state"] not in {"valid", "unknown"} or set(warnings) - PRICE_ONLY_UNKNOWN
                or (row["quality_state"] == "unknown" and not warnings)):
            raise ValueError("price_quality_unknown")
        if quote > receive or receive > as_of_ms or receive - quote > 120000:
            raise ValueError("snapshot_timestamp_future_or_stale")
        session = get_market_session(market, _time(quote))
        if session.session_state != "regular" or session.diagnostic_code is not None or row["market_session_state"] != "regular" or row.get("market_session_diagnostic"):
            raise ValueError("snapshot_session_unknown")
        return SnapshotRef(snapshot_id=row["id"], price=price, quote_timestamp=quote, receive_timestamp=receive,
                           quality_state=row["quality_state"], warning_codes=tuple(warnings))

    def assess(self, current, as_of: datetime) -> list[dict]:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("aware evaluation time required")
        as_of_ms = int(as_of.timestamp() * 1000)
        market = current["market"]
        diagnostics = [{"rule_id": "volatility_expansion", "state": "unsupported", "reason": "snapshot_cadence_not_authoritative"}]
        try:
            session = get_market_session(market, as_of)
            if session.session_state != "regular" or session.diagnostic_code is not None:
                raise ValueError("market_not_confirmed_regular")
            observation = self._ref(current, market, as_of_ms)
            if as_of_ms - observation.quote_timestamp > 120000:
                raise ValueError("latest_snapshot_stale")
            quote_day = get_market_session(market, _time(observation.quote_timestamp)).local_date
            midnight = datetime.combine(quote_day, datetime.min.time(), session.timezone)
            rows, truncated = self.input.history(current, as_of_ms, int(midnight.timestamp() * 1000))
        except (ValueError, InvalidOperation, OverflowError, OSError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) and re_safe_reason(str(exc)) else "snapshot_unknown"
            return [*diagnostics, *[{"rule": rule, "state": "unknown", "reason": reason} for rule in self.policy.rules]]
        for rule in self.policy.rules:
            if rule.event_type == "volatility_expansion":
                diagnostics.append({"rule": rule, "state": "unsupported", "reason": "snapshot_cadence_not_authoritative"})
                continue
            try:
                # Rapid move examines its real timestamp interval plus boundary
                # tolerance; breakout examines prior archived regular-day prices.
                boundary = observation.quote_timestamp - rule.window_seconds * 1000
                candidates = []
                for row in rows:
                    timestamp = _milliseconds(row["quote_timestamp"])
                    if rule.event_type == "rapid_price_move" and timestamp < boundary - self.policy.boundary_tolerance_ms:
                        continue
                    ref = self._ref(row, market, as_of_ms)
                    if get_market_session(market, _time(ref.quote_timestamp)).local_date == quote_day:
                        candidates.append(ref)
                timeline = [*candidates, observation]
                gaps = [timeline[i].quote_timestamp - timeline[i - 1].quote_timestamp for i in range(1, len(timeline))]
                if any(gap <= 0 for gap in gaps):
                    raise ValueError("duplicate_or_out_of_order_timestamp")
                if any(timeline[i].receive_timestamp < timeline[i - 1].receive_timestamp for i in range(1, len(timeline))):
                    raise ValueError("receipt_clock_regressed")
                if not candidates or observation.quote_timestamp - candidates[-1].quote_timestamp > self.policy.max_gap_ms:
                    raise ValueError("sparse_snapshot_history")
                if rule.event_type == "rapid_price_move":
                    baselines = [ref for ref in candidates if ref.quote_timestamp <= boundary]
                    if not baselines or boundary - baselines[-1].quote_timestamp > self.policy.boundary_tolerance_ms:
                        raise ValueError("window_boundary_missing")
                    baseline = baselines[-1]
                    relevant = [ref for ref in candidates if ref.quote_timestamp >= baseline.quote_timestamp] + [observation]
                    if any(relevant[i].quote_timestamp - relevant[i - 1].quote_timestamp > self.policy.max_gap_ms for i in range(1, len(relevant))):
                        raise ValueError("sparse_snapshot_history")
                else:
                    if truncated:
                        raise ValueError("intraday_history_truncated")
                    if len(candidates) < self.policy.min_breakout_samples:
                        raise ValueError("insufficient_breakout_history")
                    high, low = max(candidates, key=lambda ref: ref.price), min(candidates, key=lambda ref: ref.price)
                    baseline = high if observation.price >= high.price else low if observation.price <= low.price else high
                change = observation.price - baseline.price
                fraction = change / baseline.price
                triggered = abs(fraction) >= rule.threshold
                if rule.event_type == "intraday_breakout":
                    triggered = ((observation.price > high.price and fraction >= rule.threshold)
                                 or (observation.price < low.price and -fraction >= rule.threshold))
                evidence = EventEvidence(current=observation, baseline=(baseline,), sample_count=len(timeline),
                                         maximum_gap_ms=max(gaps, default=0),
                                         baseline_scope="timestamp_boundary" if rule.event_type == "rapid_price_move" else "prior_archived_intraday_prices",
                                         history_truncated=truncated, medium_multiple=self.policy.medium_multiple,
                                         high_multiple=self.policy.high_multiple, trigger_multiple=abs(fraction) / rule.threshold)
                multiple = evidence.trigger_multiple
                severity = "high" if multiple >= self.policy.high_multiple else "medium" if multiple >= self.policy.medium_multiple else "low"
                diagnostics.append({"rule": rule, "state": "triggered" if triggered else "normal",
                                    "direction": "up" if fraction >= 0 else "down", "severity": severity,
                                    "observation": observation, "baseline": baseline,
                                    "change": change, "fraction": fraction, "evidence": evidence})
            except (ValueError, InvalidOperation, OverflowError, OSError) as exc:
                diagnostics.append({"rule": rule, "state": "unknown", "reason": str(exc) if re_safe_reason(str(exc)) else "snapshot_unknown"})
        return diagnostics

    def _apply(self, db, current, assessment, as_of):
        rule = assessment.get("rule")
        if rule is None or assessment["state"] not in {"triggered", "normal"}:
            return None, assessment["state"]
        observation = assessment["observation"]
        emitted = None
        state = "normal"
        for direction in ("up", "down"):
            key = _digest((current["symbol"], current["market"], rule.rule_id, self.policy.version, direction))
            found = db.execute("SELECT payload FROM anomaly_episodes WHERE episode_key=?", (key,)).fetchone()
            episode = json.loads(found[0]) if found else None
            trigger = assessment["state"] == "triggered" and assessment["direction"] == direction
            if not trigger:
                if episode and episode["active"]:
                    episode.update(active=False, status="resolved", closed_at=observation.quote_timestamp,
                                   last_snapshot_id=current["id"], last_quote_timestamp=observation.quote_timestamp)
                else:
                    continue
            else:
                if episode and observation.quote_timestamp <= episode["last_quote_timestamp"]:
                    return None, "episode_out_of_order"
                if episode and not episode["active"] and observation.quote_timestamp - episode["closed_at"] < self.policy.cooldown_ms:
                    state = "cooldown"
                    continue
                first = not episode or not episode["active"] or observation.quote_timestamp - episode["last_quote_timestamp"] > self.policy.episode_expiry_ms
                if first:
                    episode = {"episode_id": _digest((key, current["id"])), "active": True,
                               "peak_severity": assessment["severity"], "status": "first_trigger", "closed_at": None}
                    state = "first_trigger"
                elif SEVERITIES[assessment["severity"]] > SEVERITIES[episode["peak_severity"]]:
                    episode.update(peak_severity=assessment["severity"], status="escalation")
                    state = "escalation"
                else:
                    episode["status"] = "sustained"
                    state = "sustained"
                episode.update(symbol=current["symbol"], market=current["market"], event_type=rule.event_type,
                               direction=direction, rule_id=rule.rule_id, rule_version=self.policy.version,
                               last_snapshot_id=current["id"], last_quote_timestamp=observation.quote_timestamp,
                               current_severity=assessment["severity"], current_change_pct=str(assessment["fraction"]))
                if state != "sustained":
                    baseline = assessment["baseline"]
                    emitted = AnomalyEvent(event_id=_digest((episode["episode_id"], current["id"], state)),
                        episode_id=episode["episode_id"], symbol=current["symbol"], market=current["market"],
                        event_type=rule.event_type, direction=direction, severity=assessment["severity"], status=state,
                        detected_at=as_of, window_start=_time(baseline.quote_timestamp), window_end=_time(observation.quote_timestamp),
                        observed_value=observation.price, baseline_value=baseline.price, change_value=assessment["change"],
                        change_pct=assessment["fraction"], threshold=rule.threshold, evidence=assessment["evidence"],
                        rule_id=rule.rule_id, rule_version=self.policy.version)
                    db.execute("INSERT OR IGNORE INTO anomaly_events(event_id,episode_id,symbol,market,event_type,severity,detected_at,payload) VALUES (?,?,?,?,?,?,?,?)",
                               (emitted.event_id, emitted.episode_id, emitted.symbol, emitted.market, emitted.event_type,
                                emitted.severity, int(as_of.timestamp() * 1000), emitted.model_dump_json()))
            db.execute("INSERT OR REPLACE INTO anomaly_episodes VALUES (?,?,?,?)", (key, current["symbol"], current["market"], json.dumps(episode)))
        return emitted, state

    def run_once(self, as_of: datetime, *, limit: int = 100, start_from_latest: bool = True) -> dict:
        if as_of.tzinfo is None or as_of.utcoffset() is None or type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("aware as_of and bounded batch limit required")
        try:
            with closing(self.store.connect()) as db, db:
                cursor = db.execute("SELECT last_id FROM anomaly_cursors WHERE ruleset=?", (self.policy.version,)).fetchone()
                if cursor is None:
                    checkpoint = self.input.latest_id() if start_from_latest else 0
                    db.execute("INSERT INTO anomaly_cursors VALUES (?,?)", (self.policy.version, checkpoint))
                else:
                    checkpoint = cursor[0]
                rows = self.input.page(checkpoint, limit)
                events, diagnostics = [], []
                for row in rows:
                    for assessment in self.assess(row, as_of):
                        event, state = self._apply(db, row, assessment, as_of)
                        if event:
                            events.append(event.model_dump(mode="json"))
                        diagnostics.append({"snapshot_id": row["id"], "rule_id": assessment.get("rule_id") or assessment["rule"].rule_id,
                                            "state": state, "reason": assessment.get("reason")})
                    checkpoint = row["id"]
                db.execute("UPDATE anomaly_cursors SET last_id=? WHERE ruleset=?", (checkpoint, self.policy.version))
            return {"processed": len(rows), "events": events, "diagnostics": diagnostics[-100:], "checkpoint": checkpoint,
                    "processed_by_market": {market: sum(row["market"] == market for row in rows) for market in ("CN", "HK", "US")}}
        except (sqlite3.Error, OSError, ValueError, InvalidOperation, OverflowError):
            return {"processed": 0, "events": [], "diagnostics": [{"state": "unknown", "reason": "anomaly_storage_or_input_unavailable"}], "checkpoint": None}


def re_safe_reason(value: str) -> bool:
    # Only our fixed, lower-case diagnostic codes, not SQL/path/SDK messages.
    return bool(value) and len(value) <= 80 and all(char in "abcdefghijklmnopqrstuvwxyz_" for char in value)
