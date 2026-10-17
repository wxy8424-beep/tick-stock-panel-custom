"""Closed, versioned boundaries for a future read-only Damon agent."""
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Market = Literal["CN", "HK", "US"]
DataMode = Literal["real_cache", "historical", "preview", "simulation"]
TaskStatus = Literal["pending", "running", "completed", "blocked", "cancelled", "error"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1


class ProfileReference(Contract):
    # Only this non-network profile is allowed in Phase 1. No endpoint/secret fields.
    profile_id: Literal["damon.mock"] = "damon.mock"


class ResearchContext(Contract):
    market: Market
    data_mode: DataMode
    as_of: AwareDatetime


class EvidenceReference(Contract):
    evidence_id: str = Field(min_length=1, max_length=128)
    context: ResearchContext
    source: Literal["cache", "archive", "synthetic_fixture", "simulated_event"]
    is_production: bool = False
    summary: str = Field(max_length=2000)
    missing_reason: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def provenance(self):
        expected = {"real_cache": "cache", "historical": "archive",
                    "preview": "synthetic_fixture", "simulation": "simulated_event"}
        if self.source != expected[self.context.data_mode]:
            raise ValueError("evidence_mode_conflict")
        if self.context.data_mode in {"preview", "simulation"} and self.is_production:
            raise ValueError("nonproduction_evidence_required")
        return self


class Conversation(Contract):
    session_id: str = Field(min_length=1, max_length=128)
    turn_id: str = Field(min_length=1, max_length=128)
    profile: ProfileReference = ProfileReference()
    context: ResearchContext
    status: TaskStatus = "pending"


class ResearchTask(Contract):
    task_id: str = Field(min_length=1, max_length=128)
    status: TaskStatus = "pending"
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=20)
    missing_reason: str | None = Field(default=None, max_length=200)


class ToolCall(Contract):
    call_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    context: ResearchContext
    status: TaskStatus = "pending"


class ToolOutput(Contract):
    summary: str = Field(max_length=2000)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=20)


class ToolResult(Contract):
    request_id: str
    status: TaskStatus
    code: Literal["ok", "unregistered", "write_denied", "context_conflict", "budget",
                  "timeout", "deadline", "turn_closed", "concurrency_limit",
                  "cancelled", "output_limit", "tool_error"]
    output: ToolOutput | None = None
    cleanup_state: Literal["not_needed", "finished", "still_running"] = "not_needed"
