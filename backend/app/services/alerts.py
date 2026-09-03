"""Alert policy: decide whether a risk assessment warrants an SMS, then send + record it.

Rules (in order):
  1. ``force`` -> always send (manual button on the dashboard).
  2. Overall level below ``ALERT_MIN_LEVEL`` and no insurance trigger -> skip.
  3. No alert ever sent for the farm -> send ("first_alert").
  4. Level differs from the last sent alert -> send ("level_changed").
  5. Insurance trigger newly met -> send ("insurance_trigger").
  6. Last alert younger than ``ALERT_DEDUPE_HOURS`` -> skip ("duplicate_within_window").
  7. Otherwise -> send ("repeat_after_window").
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.services.sms import SmsSender, fit_sms, send_sms

log = logging.getLogger("farmshield.alerts")

LEVEL_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


@dataclass
class AlertDecision:
    should_send: bool
    reason: str
    message: str
    language: str
    recipient: str
    level: str
    score: int
    assessment_id: int
    last_alert_id: int | None = None
    last_alert_at: datetime | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def last_sent_alert(db: Session, farm_id: int) -> models.Alert | None:
    return db.scalar(
        select(models.Alert)
        .where(models.Alert.farm_id == farm_id, models.Alert.status == "sent")
        .order_by(models.Alert.created_at.desc(), models.Alert.id.desc())
        .limit(1)
    )


def build_message(assessment: models.RiskAssessment, language: str) -> str:
    advice = (assessment.result or {}).get("advice", {})
    text = advice.get("sms_sw" if language == "sw" else "sms_en") or advice.get("sms_en") or (
        f"FarmShield: risk {assessment.overall_level} ({assessment.overall_score}/100). {assessment.advice_en or ''}"
    )
    return fit_sms(text)


def decide(
    db: Session,
    farm: models.Farm,
    assessment: models.RiskAssessment,
    *,
    language: str | None = None,
    force: bool = False,
    now: datetime | None = None,
) -> AlertDecision:
    settings = get_settings()
    now = now or datetime.now(timezone.utc)
    lang = language or farm.farmer.language or "en"
    base = dict(
        message=build_message(assessment, lang),
        language=lang,
        recipient=farm.farmer.phone,
        level=assessment.overall_level,
        score=assessment.overall_score,
        assessment_id=assessment.id,
    )
    last = last_sent_alert(db, farm.id)
    if last is not None:
        base["last_alert_id"] = last.id
        base["last_alert_at"] = _as_utc(last.created_at)

    if force:
        return AlertDecision(True, "forced", **base)

    min_rank = LEVEL_RANK.get(settings.alert_min_level.upper(), 1)
    if LEVEL_RANK[assessment.overall_level] < min_rank and not assessment.insurance_triggered:
        return AlertDecision(False, f"below_alert_threshold:{assessment.overall_level}<{settings.alert_min_level.upper()}", **base)

    if last is None:
        return AlertDecision(True, "first_alert", **base)

    prev = last.assessment
    prev_level = prev.overall_level if prev else None
    if prev_level != assessment.overall_level:
        return AlertDecision(True, f"level_changed:{prev_level or 'unknown'}->{assessment.overall_level}", **base)
    if assessment.insurance_triggered and not (prev and prev.insurance_triggered):
        return AlertDecision(True, "insurance_trigger", **base)

    age = now - _as_utc(last.created_at)
    window = timedelta(hours=settings.alert_dedupe_hours)
    if age < window:
        return AlertDecision(False, f"duplicate_within_window:{settings.alert_dedupe_hours}h", **base)
    return AlertDecision(True, "repeat_after_window", **base)


def send_alert(
    db: Session,
    farm: models.Farm,
    assessment: models.RiskAssessment,
    decision: AlertDecision,
    *,
    message: str | None = None,
    sender: SmsSender | None = None,
) -> models.Alert:
    """Deliver the SMS and persist an Alert row (status sent | failed)."""
    text = fit_sms(message) if message else decision.message
    result = send_sms(decision.recipient, text, sender=sender)
    row = models.Alert(
        farm_id=farm.id,
        assessment_id=assessment.id,
        channel="sms",
        recipient=decision.recipient,
        language=decision.language,
        message=text,
        status=result.status,
        provider=result.provider,
        provider_response=result.to_dict(),
        trigger_reason=decision.reason[:120],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log.info("Alert %s for farm %s: %s via %s%s", row.id, farm.id, decision.reason, result.provider, " (fallback)" if result.fallback else "")
    return row


def alert_payload(row: models.Alert) -> dict:
    resp = row.provider_response or {}
    source = "fallback" if resp.get("fallback") else row.provider
    return {
        "id": row.id,
        "farm_id": row.farm_id,
        "assessment_id": row.assessment_id,
        "channel": row.channel,
        "recipient": row.recipient,
        "language": row.language,
        "message": row.message,
        "chars": len(row.message),
        "status": row.status,
        "provider": row.provider,
        "source": source,
        "trigger_reason": row.trigger_reason,
        "provider_message_id": resp.get("message_id"),
        "error": resp.get("error"),
        "created_at": _as_utc(row.created_at),
    }


def notify_if_warranted(db: Session, farm: models.Farm, assessment: models.RiskAssessment) -> models.Alert | None:
    """Convenience for automated paths (scenario switch): send only when the policy says so."""
    d = decide(db, farm, assessment)
    if not d.should_send:
        log.debug("No alert for farm %s: %s", farm.id, d.reason)
        return None
    return send_alert(db, farm, assessment, d)
