"""Suppress SDK wire diagnostics, never application/business logs.

Logger filters do not propagate to descendants. List the installed SDK's concrete
loggers explicitly and include already-created descendants when a client starts.
Filters (rather than levels) also survive OPENAI_LOG=debug and root DEBUG settings.
Review this list and the real-SDK MockTransport tests on dependency upgrades.
"""
import logging

_NAMESPACES = ("openai", "httpx", "httpcore")
_LOGGERS = (
    "openai", "openai._base_client", "openai._legacy_response", "openai._response",
    "openai.lib.parsing", "openai.resources.responses.responses",
    "openai.resources.uploads.uploads", "openai.resources.realtime.realtime",
    "openai.resources.beta.realtime.realtime", "openai.audio.transcriptions",
    "httpx", "httpcore", "httpcore.connection", "httpcore.http11", "httpcore.http2",
    "httpcore.proxy", "httpcore.socks",
)


class _SuppressSDKRecords(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return False


_FILTER = _SuppressSDKRecords()


def suppress_sdk_wire_logs() -> None:
    names = set(_LOGGERS)
    names.update(name for name in tuple(logging.Logger.manager.loggerDict)
                 if name.startswith(tuple(f"{prefix}." for prefix in _NAMESPACES)))
    for name in names:
        logging.getLogger(name).addFilter(_FILTER)
