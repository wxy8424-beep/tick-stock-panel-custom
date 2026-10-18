"""Server-owned profiles; metadata never exposes endpoint or credential references."""
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from app import secrets_store
from app.config import settings


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    profile_id: str = Field(pattern=r"^[a-zA-Z0-9._-]{1,64}$")
    display_name: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=128)
    protocol: Literal["chat_completions", "responses"]
    config_ref: Literal["existing_ai"] = "existing_ai"
    credential_ref: Literal["ai_api_key"] = "ai_api_key"
    enabled: bool = True
    text_stream: bool = True


class ChatError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, repr=False)
class Snapshot:
    profile: Profile
    base_url: str = field(repr=False)
    api_key: str = field(repr=False)
    user_agent: str = field(repr=False)
    max_tokens: int = 2048
    context_window: int = 128000


def configuration():
    # One deep copy, one read: fields cannot change halfway through resolution.
    stored = secrets_store.load()

    def value(name):
        return stored.get(name) or getattr(settings, name)

    raw = stored.get("damon_profiles")
    try:
        protocol = value("ai_protocol")
        if protocol not in {"chat_completions", "responses"}:
            protocol = "chat_completions"  # Same legacy fallback as current_ai_protocol.
        profiles = [Profile.model_validate(item) for item in raw] if raw is not None else [Profile(
            profile_id="damon.default", display_name="现有 AI 配置", model=value("ai_model"),
            protocol=protocol, enabled=value("ai_provider") != "codex_cli")]
        if len(profiles) > 16 or len({p.profile_id for p in profiles}) != len(profiles):
            raise ValueError("invalid_profiles")
        key = str(value("ai_api_key") or "")
        if key and any(key in text for p in profiles for text in
                       (p.profile_id, p.display_name, p.model)):
            raise ValueError("sensitive_profile_metadata")
    except Exception:  # noqa: BLE001 - never expose configuration input
        raise ChatError("profile_configuration") from None
    return profiles, value


def metadata():
    profiles, value = configuration()
    configured = bool(value("ai_api_key"))
    return [{"profile_id": p.profile_id, "display_name": p.display_name, "model": p.model,
             "protocol": p.protocol, "enabled": p.enabled, "text_stream": p.text_stream,
             "configured": configured}
            for p in profiles]


def resolve(profile_id: str) -> Snapshot:
    profiles, value = configuration()
    profile = next((p for p in profiles if p.profile_id == profile_id), None)
    if profile is None or not profile.enabled or not profile.text_stream:
        raise ChatError("profile_unavailable")
    base = str(value("ai_base_url"))
    url = urlsplit(base)
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.query or url.fragment):
        raise ChatError("unsafe_endpoint")
    key = str(value("ai_api_key") or "")
    if not key:
        raise ChatError("not_configured")
    return Snapshot(
        profile, base, key, str(value("ai_user_agent")),
        min(4096, max(1, int(value("ai_max_output_tokens")))),
        int(value("ai_context_window")),
    )
