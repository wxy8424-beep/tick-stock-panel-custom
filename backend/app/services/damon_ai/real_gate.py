"""Fail-closed Damon real egress policy. No configuration/secret/network access.

V1 deliberately has no opening mechanism: OS egress and money caps have no
machine verifier yet. Reports are observations, never authorization capabilities.
"""
from __future__ import annotations

import importlib.util
import ipaddress
import math
import os
import sys
import tempfile
import threading
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

ALLOWED_HOSTS = frozenset({"api.openai.com"})
REFERENCE_ENDPOINT = "https://api.openai.com/v1"


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNVERIFIED = "UNVERIFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CheckId(StrEnum):
    ISOLATION = "EXECUTION_ISOLATION"
    BUDGET = "REQUEST_BUDGET"
    PROMPT = "PROMPT_LIMITS"
    ENDPOINT = "ENDPOINT_ALLOWLIST"
    PROXY = "PROXY_ENVIRONMENT"
    EGRESS = "OS_EGRESS"
    COST = "COST_CAP"
    CREDENTIAL = "CREDENTIAL_AVAILABILITY"


class Reason(StrEnum):
    ISOLATION_MISSING = "isolation_unverified"
    ISOLATION_INVALID = "isolation_invalid"
    ISOLATION_OBSERVED = "isolated_preflight_observed"
    BUDGET_MISSING = "runtime_budget_missing"
    BUDGET_CLOSED = "runtime_budget_closed"
    BUDGET_BUSY = "runtime_budget_busy"
    BUDGET_PRESENT = "server_budget_present"
    PROMPT_MISSING = "request_not_available"
    PROMPT_INVALID = "prompt_or_output_limit"
    PROMPT_VALID = "prompt_within_limits"
    ENDPOINT_MISSING = "endpoint_not_available"
    ENDPOINT_DENIED = "endpoint_denied"
    ENDPOINT_ALLOWED = "endpoint_allowlisted_not_dns_verified"
    PROXY_DISABLED = "dedicated_trust_env_false"
    EGRESS_MISSING = "os_egress_verifier_missing"
    COST_MISSING = "cost_cap_verifier_missing"
    REFERENCE_MISSING = "credential_reference_missing"
    REFERENCE_PRESENT = "credential_reference_structural_only"


@dataclass(frozen=True)
class Check:
    check_id: CheckId
    status: Status
    reason_code: Reason
    evidence: tuple[str, ...] = ()
    required: bool = True

    def to_dict(self):
        return {"check_id": self.check_id.value, "status": self.status.value,
                "reason_code": self.reason_code.value, "human_summary": self.reason_code.value.replace("_", " "),
                "evidence": list(self.evidence), "required": self.required}


@dataclass(frozen=True)
class Report:
    checks: tuple[Check, ...] = ()

    @property
    def overall_status(self):
        if len(self.checks) != len(CheckId) or {c.check_id for c in self.checks} != set(CheckId):
            return Status.UNVERIFIED
        if any(c.required and c.status == Status.FAIL for c in self.checks):
            return Status.FAIL
        if any(c.required and c.status == Status.UNVERIFIED for c in self.checks):
            return Status.UNVERIFIED
        return Status.PASS

    @property
    def ready(self):
        return self.overall_status == Status.PASS

    def to_dict(self):
        return {"overall_status": self.overall_status.value, "ready": self.ready,
                "checks": [c.to_dict() for c in self.checks]}


class GateClosedError(RuntimeError):
    def __init__(self, report: Report):
        self.report = report
        super().__init__("real_model_gate_closed")


def endpoint_check(endpoint):
    """ASCII DNS names only; no DNS lookup, IDN, encoded authority or custom hosts."""
    if endpoint is None:
        return Check(CheckId.ENDPOINT, Status.UNVERIFIED, Reason.ENDPOINT_MISSING)
    valid = False
    try:
        if (isinstance(endpoint, str) and len(endpoint) <= 512 and endpoint.isascii()
                and not any(ord(c) <= 32 or ord(c) == 127 for c in endpoint)
                and not any(c in endpoint for c in ("\\", "%", "?", "#"))):
            url = urlsplit(endpoint)
            host = (url.hostname or "").removesuffix(".").lower()
            try:
                ipaddress.ip_address(host)
            except ValueError:
                literal = False
            else:
                literal = True
            valid = (url.scheme == "https" and url.username is None and url.password is None
                     and url.port in {None, 443} and not literal
                     and not any(part.startswith("xn--") for part in host.split("."))
                     and host in ALLOWED_HOSTS and url.path in {"", "/", "/v1", "/v1/"})
    except (TypeError, ValueError, UnicodeError):
        valid = False
    return Check(CheckId.ENDPOINT, Status.PASS if valid else Status.FAIL,
                 Reason.ENDPOINT_ALLOWED if valid else Reason.ENDPOINT_DENIED)


def prompt_check(messages, max_tokens):
    """Count actual complete message contents, including system instructions."""
    if messages is None:
        return Check(CheckId.PROMPT, Status.UNVERIFIED, Reason.PROMPT_MISSING)
    valid = (type(max_tokens) is int and 1 <= max_tokens <= 512
             and isinstance(messages, (list, tuple)) and 1 <= len(messages) <= 24
             and all(isinstance(m, dict) and isinstance(m.get("role"), str)
                     and m.get("role") in {"system", "user", "assistant"}
                     and isinstance(m.get("content"), str) for m in messages))
    if valid:
        valid = (messages[-1]["role"] == "user" and 1 <= len(messages[-1]["content"]) <= 1000
                 and sum(len(m["content"]) for m in messages) <= 3000)
    return Check(CheckId.PROMPT, Status.PASS if valid else Status.FAIL,
                 Reason.PROMPT_VALID if valid else Reason.PROMPT_INVALID)


class Outcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    UNCERTAIN = "cancel_uncertain"


class SmokeBudget:
    """Process-local server admission primitive, not money or cross-worker quota."""
    def __init__(self, max_attempts=3, concurrency=1):
        if (type(max_attempts) is not int or not 1 <= max_attempts <= 3
                or type(concurrency) is not int or concurrency != 1):
            raise ValueError("invalid_smoke_budget")
        self._lock = threading.Lock()
        self._max = max_attempts
        self._attempts = 0
        self._active = None
        self._closed = False

    def check(self):
        with self._lock:
            reason = Reason.BUDGET_CLOSED if self._closed else Reason.BUDGET_BUSY if self._active else Reason.BUDGET_PRESENT
            return Check(CheckId.BUDGET, Status.PASS if reason == Reason.BUDGET_PRESENT else Status.FAIL, reason)

    @property
    def attempts(self):
        with self._lock:
            return self._attempts

    def admit(self, messages, max_tokens):
        if prompt_check(messages, max_tokens).status != Status.PASS:
            raise ValueError("prompt_or_output_limit")
        with self._lock:
            if self._closed:
                raise RuntimeError("runtime_budget_closed")
            if self._active:
                raise RuntimeError("runtime_budget_busy")
            self._attempts += 1
            self._active = uuid4().hex
            if self._attempts >= self._max:
                self._closed = True
            return self._active

    def finish(self, lease, outcome: Outcome):
        if not isinstance(outcome, Outcome):
            raise ValueError("invalid_smoke_outcome")
        with self._lock:
            if self._active != lease or self._active is None:
                return False
            if outcome != Outcome.SUCCESS:
                self._closed = True
            if outcome != Outcome.UNCERTAIN:
                self._active = None
            return True


def isolation_check():
    """Observe the actual fresh-process bootstrap; no caller-supplied PASS flag."""
    module = sys.modules.get("damon_offline")
    sandbox = getattr(module, "ACTIVE_SANDBOX", None)
    if sandbox is None or type(sandbox) is not getattr(module, "Sandbox", None):
        return Check(CheckId.ISOLATION, Status.UNVERIFIED, Reason.ISOLATION_MISSING)
    try:
        root = sandbox.root.resolve()
        data = Path(os.environ.get("DATA_DIR", "")).resolve()
        env = Path(os.environ.get("TICKFLOW_ENV_FILE", "")).resolve()
        prefixes = sandbox.blocked_imports
        try:
            importlib.util.find_spec("app.main")  # Finder only: never execute app.main.
        except ImportError:
            import_guard = True
        else:
            import_guard = False
        valid = (type(sandbox.temp) is tempfile.TemporaryDirectory and sandbox.temp._finalizer.alive
                 and Path(sandbox.temp.name).resolve() == root and root.name.startswith("damon-offline-")
                 and data == root / "data" and data.is_dir()
                 and env == root / "isolated.env" and env.is_file() and env.stat().st_size == 0
                 and import_guard and os.environ.get("WEB_CONCURRENCY") == "1" and "--reload" not in sys.argv
                 and not any(name == p or name.startswith(p + ".") for name in sys.modules for p in prefixes)
                 and all(t is threading.main_thread() for t in threading.enumerate()))
    except (OSError, AttributeError, TypeError, ValueError):
        valid = False
    return Check(CheckId.ISOLATION, Status.PASS if valid else Status.FAIL,
                 Reason.ISOLATION_OBSERVED if valid else Reason.ISOLATION_INVALID,
                 ("fresh_asgi_only_bootstrap",) if valid else ())


def http_options(timeout):
    if type(timeout) not in {int, float} or not math.isfinite(timeout) or not 0 < timeout <= 60:
        raise ValueError("invalid_smoke_timeout")
    return {"trust_env": False, "follow_redirects": False, "timeout": timeout}


def evaluate(*, endpoint=None, credential_ref=None, budget=None, messages=None, max_tokens=512):
    """Pure policy + local observation; no secret value or operator override accepted."""
    return Report((
        isolation_check(),
        budget.check() if type(budget) is SmokeBudget else Check(CheckId.BUDGET, Status.UNVERIFIED, Reason.BUDGET_MISSING),
        prompt_check(messages, max_tokens),
        endpoint_check(endpoint),
        Check(CheckId.PROXY, Status.PASS, Reason.PROXY_DISABLED, ("dedicated_client_options",)),
        Check(CheckId.EGRESS, Status.UNVERIFIED, Reason.EGRESS_MISSING),
        Check(CheckId.COST, Status.UNVERIFIED, Reason.COST_MISSING),
        Check(CheckId.CREDENTIAL, Status.PASS if credential_ref == ("existing_ai", "ai_api_key") else Status.FAIL,
              Reason.REFERENCE_PRESENT if credential_ref == ("existing_ai", "ai_api_key") else Reason.REFERENCE_MISSING,
              ("structure_only_not_key_validity",)),
    ))


def require_real_client():
    # No report, env flag, operator string or caller capability can open V1.
    # Future OS/cost integrations must be separately reviewed at this boundary.
    report = evaluate()
    if not report.ready:
        raise GateClosedError(report)
    raise GateClosedError(report)  # Defense in depth: this version never authorizes real egress.
