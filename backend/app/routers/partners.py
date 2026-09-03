"""Partner API (/api/v1): API-key protected risk data for insurers, banks, SACCOs and agribusinesses."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.auth import require_api_key
from app.db import get_db
from app.engine import Policy, check_trigger, derive_stage
from app.schemas import (
    ApiError,
    BulkRiskOut,
    FarmOut,
    PartnerInfoOut,
    RiskOut,
    TriggerCheckIn,
    TriggerCheckOut,
)
from app.services.assessment import farm_payload, fetch_readings, get_or_create_latest, risk_payload, run_assessment

log = logging.getLogger("farmshield.partners")

router = APIRouter(
    prefix="/api/v1",
    tags=["partners"],
    dependencies=[Depends(require_api_key)],
    responses={401: {"model": ApiError, "description": "Missing or invalid X-API-Key"}},
)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@router.get("/me", response_model=PartnerInfoOut, summary="Who am I?", description="Echoes the authenticated partner client. Handy for verifying a key.")
def me(client: models.ApiClient = Depends(require_api_key)) -> dict:
    return {
        "client": client.name,
        "organisation_type": client.organisation_type,
        "request_count": client.request_count,
        "last_used_at": client.last_used_at,
    }


@router.get("/farms", response_model=list[FarmOut], summary="Portfolio: all registered farms with latest risk summary")
def portfolio(db: Session = Depends(get_db)) -> list[dict]:
    farms = db.scalars(select(models.Farm).order_by(models.Farm.id)).all()
    return [farm_payload(db, f) for f in farms]


@router.get(
    "/risk/bulk",
    response_model=BulkRiskOut,
    summary="Bulk risk scores for a portfolio",
    description="Comma-separated `farm_ids`. Unknown ids are reported in `errors` rather than failing the whole call.",
)
def partner_risk_bulk(
    farm_ids: str = Query(..., description="Comma-separated farm ids, e.g. `1,2,3`", examples=["1,2,3"]),
    fresh: bool = Query(False, description="Re-run the engine for every farm"),
    db: Session = Depends(get_db),
) -> dict:
    ids: list[int] = []
    errors: list[dict] = []
    for raw in farm_ids.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            ids.append(int(raw))
        except ValueError:
            errors.append({"farm_id": raw, "error": "not an integer"})
    results: list[dict] = []
    for fid in ids:
        farm = db.get(models.Farm, fid)
        if farm is None:
            errors.append({"farm_id": fid, "error": "not found"})
            continue
        try:
            row = run_assessment(db, farm) if fresh else get_or_create_latest(db, farm)
            results.append(risk_payload(row))
        except Exception as exc:  # noqa: BLE001
            log.warning("bulk: farm %s failed: %s", fid, exc)
            errors.append({"farm_id": fid, "error": str(exc)})
    high = sum(1 for r in results if r["overall"]["level"] == "HIGH")
    triggered = sum(1 for r in results if r["insurance_trigger"]["triggered"])
    return {
        "count": len(results),
        "summary": {
            "high_risk": high,
            "medium_risk": sum(1 for r in results if r["overall"]["level"] == "MEDIUM"),
            "low_risk": sum(1 for r in results if r["overall"]["level"] == "LOW"),
            "insurance_triggered": triggered,
            "mean_score": round(sum(r["overall"]["score"] for r in results) / len(results), 1) if results else None,
        },
        "results": results,
        "errors": errors,
    }


@router.get(
    "/risk/{farm_id}",
    response_model=RiskOut,
    summary="Dynamic risk score for one farm",
    description=(
        "Returns the latest Farm Risk Score: overall 0-100 + label, four sub-scores with reasons, growth stage, "
        "the default drought insurance trigger, advice text, timestamp and data sources. "
        "Set `fresh=true` to force a new assessment against current weather."
    ),
    responses={404: {"model": ApiError}},
)
def partner_risk(
    farm_id: int,
    fresh: bool = Query(False, description="Re-run the engine now instead of returning the stored latest assessment"),
    db: Session = Depends(get_db),
) -> dict:
    farm = db.get(models.Farm, farm_id)
    if farm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Farm {farm_id} not found")
    row = run_assessment(db, farm) if fresh else get_or_create_latest(db, farm)
    return risk_payload(row)


@router.post(
    "/insurance/check-trigger",
    response_model=TriggerCheckOut,
    summary="Evaluate a parametric policy against observed weather",
    description=(
        "Supply your own policy definition (drought deficit, excess rain or heat days) and FarmShield evaluates it "
        "against the farm's observed readings and growth stage, returning `triggered`, the evidence and a confidence."
    ),
    responses={404: {"model": ApiError}, 422: {"model": ApiError}},
)
def check_insurance_trigger(body: TriggerCheckIn, db: Session = Depends(get_db)) -> dict:
    farm = db.get(models.Farm, body.farm_id)
    if farm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Farm {body.farm_id} not found")
    readings, source, scenario = fetch_readings(farm, body.scenario)
    stage = derive_stage(farm.crop, farm.planting_date, date.today())
    policy = Policy(**body.policy.model_dump())
    try:
        result = check_trigger(readings, farm.crop, stage, policy)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return {
        "farm_id": farm.id,
        "farm_name": farm.name,
        "crop": farm.crop,
        "stage": stage.name,
        **result.to_dict(),
        "assessed_at": _iso(datetime.now(timezone.utc)),
        "scenario": scenario,
        "data_sources": [source],
    }
