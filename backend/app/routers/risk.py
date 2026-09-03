"""Risk endpoints: assess a farm, read the latest score, history, and the demo scenario switch."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.db import get_db
from app.engine.sample_data import SCENARIOS
from app.providers.weather import get_weather_provider, scenario_state
from app.routers.farms import get_farm_or_404
from app.schemas import ApiError, RiskHistoryItem, RiskOut, Scenario, ScenarioOut, ScenarioSwitchOut, ScenarioUpdate
from app.services.assessment import get_or_create_latest, risk_payload, risk_summary, run_assessment

log = logging.getLogger("farmshield.risk")
router = APIRouter(tags=["risk"])


@router.post(
    "/farms/{farm_id}/assess",
    response_model=RiskOut,
    summary="Run the risk engine for a farm now",
    description=(
        "Pulls the last 30 days of readings for the farm location, derives the growth stage, scores "
        "drought / flood / heat / crop health, evaluates the default drought insurance trigger and generates "
        "advice. The result is stored and returned."
    ),
    responses={404: {"model": ApiError}, 422: {"model": ApiError}},
)
def assess_farm(
    farm: models.Farm = Depends(get_farm_or_404),
    scenario: Scenario | None = Query(None, description="Force a mock scenario for this assessment only"),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = run_assessment(db, farm, scenario)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return risk_payload(row)


@router.get(
    "/farms/{farm_id}/risk",
    response_model=RiskOut,
    summary="Latest Farm Risk Score",
    description="Returns the most recent stored assessment; runs one if the farm has never been assessed.",
    responses={404: {"model": ApiError}},
)
def get_risk(farm: models.Farm = Depends(get_farm_or_404), db: Session = Depends(get_db)) -> dict:
    return risk_payload(get_or_create_latest(db, farm))


@router.get(
    "/farms/{farm_id}/risk/history",
    response_model=list[RiskHistoryItem],
    summary="Assessment history (newest first)",
    responses={404: {"model": ApiError}},
)
def risk_history(
    farm: models.Farm = Depends(get_farm_or_404),
    limit: int = Query(30, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(
        select(models.RiskAssessment)
        .where(models.RiskAssessment.farm_id == farm.id)
        .order_by(models.RiskAssessment.assessed_at.desc(), models.RiskAssessment.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "assessment_id": r.id,
            "assessed_at": r.assessed_at,
            "scenario": r.scenario,
            "stage": r.stage_name,
            "overall_score": r.overall_score,
            "overall_level": r.overall_level,
            "drought": r.drought_score,
            "flood": r.flood_score,
            "heat": r.heat_score,
            "crop_health": r.crop_health_score,
            "insurance_triggered": r.insurance_triggered,
        }
        for r in rows
    ]


# ------------------------------------------------------------ demo scenario ----

scenario_router = APIRouter(prefix="/scenario", tags=["demo"])


@scenario_router.get("", response_model=ScenarioOut, summary="Active mock weather scenario")
def get_scenario() -> dict:
    return {
        "scenario": scenario_state.current,
        "provider": get_weather_provider().name,
        "available": list(SCENARIOS),
    }


@scenario_router.put(
    "",
    response_model=ScenarioSwitchOut,
    summary="Switch the mock weather scenario (live demo)",
    description="Flips the replayed weather between normal / dry_spell / heavy_rain and, by default, re-assesses every farm so scores and SMS alerts change immediately.",
)
def set_scenario(body: ScenarioUpdate, db: Session = Depends(get_db)) -> dict:
    scenario_state.set(body.scenario)
    settings = get_settings()
    if settings.weather_provider.lower() != "mock":
        log.info("Scenario switched to %s but WEATHER_PROVIDER=%s; only used as fallback", body.scenario, settings.weather_provider)
    summaries: list[dict | None] = []
    if body.reassess:
        for farm in db.scalars(select(models.Farm).order_by(models.Farm.id)).all():
            try:
                summaries.append(risk_summary(run_assessment(db, farm)))
            except Exception as exc:  # noqa: BLE001
                log.warning("Re-assessment of farm %s failed: %s", farm.id, exc)
                summaries.append(None)
    return {"scenario": body.scenario, "reassessed": summaries}
