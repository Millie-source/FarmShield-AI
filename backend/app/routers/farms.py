"""Farmer-facing farm endpoints: register, list, get, weather history."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.schemas import ApiError, FarmCreate, FarmOut, Scenario, WeatherHistoryOut
from app.services.assessment import farm_payload, fetch_readings, run_assessment

log = logging.getLogger("farmshield.farms")
router = APIRouter(prefix="/farms", tags=["farms"])


def get_farm_or_404(farm_id: int, db: Session = Depends(get_db)) -> models.Farm:
    farm = db.get(models.Farm, farm_id)
    if farm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Farm {farm_id} not found")
    return farm


@router.post(
    "",
    response_model=FarmOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a farm",
    description=(
        "Registers a farmer (matched by phone number) and a farm plot, then runs a first risk "
        "assessment immediately so the dashboard shows a score straight away."
    ),
    responses={422: {"model": ApiError, "description": "Validation error (unknown crop, bad phone, out-of-bounds location)"}},
)
def create_farm(body: FarmCreate, db: Session = Depends(get_db)) -> dict:
    farmer = db.scalar(select(models.Farmer).where(models.Farmer.phone == body.phone))
    if farmer is None:
        farmer = models.Farmer(name=body.farmer_name, phone=body.phone, language=body.language)
        db.add(farmer)
        db.flush()
    else:
        farmer.name = body.farmer_name
        farmer.language = body.language
    farm = models.Farm(
        farmer_id=farmer.id,
        name=body.farm_name,
        crop=body.crop,
        planting_date=body.planting_date,
        lat=body.lat,
        lon=body.lon,
        area_ha=body.area_ha,
    )
    db.add(farm)
    db.commit()
    db.refresh(farm)
    try:
        run_assessment(db, farm)
    except Exception as exc:  # noqa: BLE001 - registration must succeed even if assessment fails
        log.warning("Initial assessment for farm %s failed: %s", farm.id, exc)
    return farm_payload(db, farm)


@router.get("", response_model=list[FarmOut], summary="List farms with their latest risk summary")
def list_farms(db: Session = Depends(get_db)) -> list[dict]:
    farms = db.scalars(select(models.Farm).order_by(models.Farm.id)).all()
    return [farm_payload(db, f) for f in farms]


@router.get(
    "/{farm_id}",
    response_model=FarmOut,
    summary="Get one farm",
    responses={404: {"model": ApiError}},
)
def get_farm(farm: models.Farm = Depends(get_farm_or_404), db: Session = Depends(get_db)) -> dict:
    return farm_payload(db, farm)


@router.delete("/{farm_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a farm", responses={404: {"model": ApiError}})
def delete_farm(farm: models.Farm = Depends(get_farm_or_404), db: Session = Depends(get_db)) -> None:
    db.delete(farm)
    db.commit()


@router.get(
    "/{farm_id}/weather",
    response_model=WeatherHistoryOut,
    summary="Daily weather history used for scoring",
    description="Readings from the active provider (JKUAT Conduit station or the mock replay). Pass `scenario` to preview a mock scenario without switching it globally.",
    responses={404: {"model": ApiError}},
)
def farm_weather(
    farm: models.Farm = Depends(get_farm_or_404),
    days: int = Query(30, ge=1, le=30, description="Number of days of history"),
    scenario: Scenario | None = Query(None, description="Force a mock scenario for this call"),
) -> dict:
    readings, source, _ = fetch_readings(farm, scenario, days=days)
    return {
        "farm_id": farm.id,
        "source": source,
        "days": len(readings),
        "readings": [r.__dict__ for r in readings],
    }
