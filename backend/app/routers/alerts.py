"""Farmer SMS alerts: preview the exact message, send it (with dedupe), list history."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.routers.farms import get_farm_or_404
from app.schemas import AlertOut, AlertPreviewOut, AlertRequest, AlertSendOut, ApiError
from app.services import alerts as svc
from app.services.assessment import get_or_create_latest
from app.services.sms import get_sms_sender

log = logging.getLogger("farmshield.alerts")
router = APIRouter(prefix="/farms/{farm_id}/alerts", tags=["alerts"], responses={404: {"model": ApiError}})

_BODY = Body(default=None, description="Optional overrides; send `{}` or nothing for defaults")


@router.post(
    "/preview",
    response_model=AlertPreviewOut,
    summary="Preview the SMS that would be sent",
    description=(
        "Builds the exact <=160-char message from the latest assessment (running one if needed) and applies the "
        "alert policy: no SMS for LOW risk unless an insurance trigger fired, no repeat within "
        "`ALERT_DEDUPE_HOURS` unless the risk level changed. Nothing is sent or stored."
    ),
)
def preview_alert(
    farm: models.Farm = Depends(get_farm_or_404),
    body: AlertRequest | None = _BODY,
    db: Session = Depends(get_db),
) -> dict:
    body = body or AlertRequest()
    assessment = get_or_create_latest(db, farm)
    d = svc.decide(db, farm, assessment, language=body.language, force=body.force)
    if body.message:
        d.message = svc.fit_sms(body.message)
    return {
        "farm_id": farm.id,
        "would_send": d.should_send,
        "chars": len(d.message),
        "sender": get_sms_sender().name,
        **d.to_dict(),
    }


@router.post(
    "/send",
    response_model=AlertSendOut,
    summary="Send an SMS alert to the farmer",
    description=(
        "Applies the same policy as `/preview`; when warranted (or `force=true`) sends via the configured sender "
        "(Africa's Talking sandbox or console) and records the alert. If the gateway fails the message is logged to "
        "the console and the alert is stored with `source: \"fallback\"` - the call still returns 200. "
        "A suppressed alert also returns 200 with `sent: false` and the reason."
    ),
)
def send_alert(
    farm: models.Farm = Depends(get_farm_or_404),
    body: AlertRequest | None = _BODY,
    db: Session = Depends(get_db),
) -> dict:
    body = body or AlertRequest()
    assessment = get_or_create_latest(db, farm)
    d = svc.decide(db, farm, assessment, language=body.language, force=body.force)
    if not d.should_send:
        return {"farm_id": farm.id, "sent": False, "reason": d.reason, "alert": None}
    row = svc.send_alert(db, farm, assessment, d, message=body.message)
    return {"farm_id": farm.id, "sent": row.status == "sent", "reason": d.reason, "alert": svc.alert_payload(row)}


@router.get("", response_model=list[AlertOut], summary="Alert history for a farm (newest first)")
def list_alerts(
    farm: models.Farm = Depends(get_farm_or_404),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(
        select(models.Alert).where(models.Alert.farm_id == farm.id).order_by(models.Alert.created_at.desc(), models.Alert.id.desc()).limit(limit)
    ).all()
    return [svc.alert_payload(r) for r in rows]
