"""SMS delivery adapters.

``SmsSender`` is the interface; ``ConsoleSender`` logs to stdout (default, zero
config) and ``AfricasTalkingSandboxSender`` uses the Africa's Talking sandbox.
``send_sms`` picks the configured sender and, if it fails for any reason (no key,
SDK missing, network down), degrades to the console so the API never 500s.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Any

from app.config import get_settings

log = logging.getLogger("farmshield.sms")

SMS_LIMIT = 160


@dataclass
class SmsResult:
    ok: bool
    provider: str  # console | africastalking
    status: str  # sent | failed
    message_id: str | None = None
    error: str | None = None
    raw: dict[str, Any] | None = field(default=None, repr=False)
    fallback: bool = False  # True when the configured sender failed and console took over

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SmsSender(ABC):
    name: str = "base"

    @abstractmethod
    def send(self, to: str, message: str) -> SmsResult:
        """Deliver ``message`` to E.164 number ``to``. Must not raise for delivery problems."""


class ConsoleSender(SmsSender):
    """Prints the SMS instead of sending it. Always succeeds."""

    name = "console"

    def send(self, to: str, message: str) -> SmsResult:
        log.info("SMS -> %s (%d chars): %s", to, len(message), message)
        print(f"\n=== SMS to {to} ({len(message)} chars) ===\n{message}\n", flush=True)
        return SmsResult(ok=True, provider=self.name, status="sent", message_id=None, raw={"echo": message})


class AfricasTalkingSandboxSender(SmsSender):
    """Africa's Talking SMS via the official SDK (sandbox by default).

    Sandbox deliveries show up in the AT simulator, not on real phones.
    """

    name = "africastalking"

    def __init__(self, username: str, api_key: str, sender_id: str = "") -> None:
        self.username = username
        self.api_key = api_key
        self.sender_id = sender_id or None
        self._sms = None

    def _client(self):
        if self._sms is None:
            import africastalking  # lazy so the SDK is optional

            africastalking.initialize(self.username, self.api_key)
            self._sms = africastalking.SMS
        return self._sms

    def send(self, to: str, message: str) -> SmsResult:
        if not self.api_key:
            return SmsResult(ok=False, provider=self.name, status="failed", error="AT_API_KEY not set")
        try:
            kwargs = {"sender_id": self.sender_id} if self.sender_id else {}
            resp = self._client().send(message, [to], **kwargs)
        except Exception as exc:  # noqa: BLE001 - never let a gateway error escape
            return SmsResult(ok=False, provider=self.name, status="failed", error=f"{type(exc).__name__}: {exc}")
        recipients = (resp or {}).get("SMSMessageData", {}).get("Recipients", []) if isinstance(resp, dict) else []
        first = recipients[0] if recipients else {}
        # AT statusCode 100/101/102 = processed / sent / queued
        ok = str(first.get("status", "")).lower() in ("success", "sent", "queued") or int(first.get("statusCode", 0) or 0) in (100, 101, 102)
        return SmsResult(
            ok=ok,
            provider=self.name,
            status="sent" if ok else "failed",
            message_id=first.get("messageId"),
            error=None if ok else (first.get("status") or (resp or {}).get("SMSMessageData", {}).get("Message") or "rejected"),
            raw=resp if isinstance(resp, dict) else {"response": str(resp)},
        )


@lru_cache
def get_sms_sender() -> SmsSender:
    s = get_settings()
    if s.sms_sender.lower() in ("africastalking", "at", "africas_talking"):
        return AfricasTalkingSandboxSender(s.at_username, s.at_api_key, s.at_sender_id)
    return ConsoleSender()


def fit_sms(text: str, limit: int = SMS_LIMIT) -> str:
    """Collapse whitespace and hard-cap to one SMS segment."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def send_sms(to: str, message: str, sender: SmsSender | None = None) -> SmsResult:
    """Send via the configured sender; on failure log the SMS to the console and flag ``fallback``."""
    sender = sender or get_sms_sender()
    result = sender.send(to, message)
    if result.ok or isinstance(sender, ConsoleSender):
        return result
    log.warning("%s SMS failed (%s); logging to console instead", sender.name, result.error)
    fb = ConsoleSender().send(to, message)
    fb.fallback = True
    fb.error = result.error
    fb.raw = {"primary": result.to_dict()}
    return fb
