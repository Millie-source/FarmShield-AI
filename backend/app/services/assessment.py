"""Assessment service: weather provider -> engine -> advice -> persisted RiskAssessment."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models
from app.db import SessionLocal
from app.engine import Policy, assess, check_trigger, derive_stage, get_crop
from app.engine.types import Reading
from app.providers.satellite.base import get_satellite_provider
from app.providers.weather import get_weather_provider
from app.services.advisor import generate_advice

log = logging.getLogger("farmshield.assessment")

# Farm-level "insurance signal" shown on every assessment. Partners can evaluate
# their own policies via POST /api/v1/insurance/check-trigger.
DEFAULT_POLICY = Policy(type="drought", window_days=21, rainfall_threshold_mm=30)
HISTORY_DAYS = 30


def _iso(dt: datetime) -> str:
    return as_utc(dt).isoformat().replace("+00:00", "Z")


def as_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def fetch_readings(farm: models.Farm, scenario: str | None = None, days: int = HISTORY_DAYS) -> tuple[list[Reading], str, str | None]:
    provider = get_weather_provider(scenario)
    readings = provider.get_history(farm.lat, farm.lon, days=days)
    return readings, provider.source_id(), provider.scenario


def _persist_readings(db: Session, farm: models.Farm, readings: list[Reading], source: str) -> None:
    db.execute(delete(models.WeatherReading).where(models.WeatherReading.farm_id == farm.id, models.WeatherReading.source == source))
    db.add_all(
        models.WeatherReading(
            farm_id=farm.id,
            source=source,
            date=r.date,
            rainfall_mm=r.rainfall_mm,
            temp_max_c=r.temp_max_c,
            temp_min_c=r.temp_min_c,
            temp_mean_c=r.temp_mean_c,
            humidity_pct=r.humidity_pct,
            wind_speed_ms=r.wind_speed_ms,
            wind_gust_ms=r.wind_gust_ms,
            heat_index_max_c=r.heat_index_max_c,
            wbgt_max_c=r.wbgt_max_c,
            light_index=r.light_index,
            soil_moisture_pct=r.soil_moisture_pct,
            synthetic=r.synthetic,
        )
        for r in readings
    )


def run_assessment(db: Session, farm: models.Farm, scenario: str | None = None, today: date | None = None) -> models.RiskAssessment:
    """Run the full pipeline for one farm and persist the result. Raises only on engine input errors."""
    today = today or date.today()
    readings, source, used_scenario = fetch_readings(farm, scenario)
    stage = derive_stage(farm.crop, farm.planting_date, today)

    sat = get_satellite_provider()
    ndvi = None
    try:
        ndvi = sat.get_ndvi(farm.lat, farm.lon, today)
    except Exception as exc:  # noqa: BLE001
        log.warning("Satellite provider failed (%s); continuing without NDVI", exc)

    a = assess(readings, farm.crop, stage, ndvi=ndvi)
    trigger = check_trigger(readings, farm.crop, stage, DEFAULT_POLICY)
    advice = generate_advice(a, trigger, farm.name, readings)

    assessed_at = datetime.now(timezone.utc)
    data_sources = [source] + ([sat.source_id()] if ndvi is not None and sat.source_id() else [])
    engine_dict = a.to_dict()

    payload = {
        "farm_id": farm.id,
        "farm_name": farm.name,
        "crop": a.crop,
        "stage": engine_dict["stage"],
        "overall": engine_dict["overall"],
        "sub_scores": engine_dict["sub_scores"],
        "insurance_trigger": trigger.to_dict(),
        "advice": advice.to_dict(),
        "assessed_at": _iso(assessed_at),
        "scenario": used_scenario,
        "data_sources": data_sources,
        "readings_used": a.readings_used,
        "window_days": a.window_days,
        "ndvi": ndvi,
        "soil_moisture_pct": a.soil_moisture_pct,
        "soil_moisture_source": a.soil_moisture_source,
        "et0_mm_day": a.et0_mm_day,
        "heat_metric": a.heat_metric,
    }

    row = models.RiskAssessment(
        farm_id=farm.id,
        assessed_at=assessed_at,
        scenario=used_scenario,
        data_sources=data_sources,
        stage_name=stage.name,
        overall_score=a.overall.score,
        overall_level=a.overall.level,
        overall_label=a.overall.label,
        drought_score=a.drought.score,
        drought_level=a.drought.level,
        flood_score=a.flood.score,
        flood_level=a.flood.level,
        heat_score=a.heat.score,
        heat_level=a.heat.level,
        crop_health_score=a.crop_health.score,
        crop_health_level=a.crop_health.level,
        crop_health_label=a.crop_health.label or "FAIR",
        insurance_triggered=trigger.triggered,
        result=payload,
        advice_en=advice.en,
        advice_sw=advice.sw,
        advice_source=advice.source,
    )
    db.add(row)
    _persist_readings(db, farm, readings, source)
    db.commit()
    db.refresh(row)
    row.result = {**payload, "assessment_id": row.id}
    db.commit()
    log.info("Assessed farm %s (%s/%s) -> %s %s [%s]", farm.id, farm.crop, stage.name, a.overall.score, a.overall.level, source)
    return row


def latest_assessment(db: Session, farm_id: int) -> models.RiskAssessment | None:
    return db.scalar(
        select(models.RiskAssessment)
        .where(models.RiskAssessment.farm_id == farm_id)
        .order_by(models.RiskAssessment.assessed_at.desc(), models.RiskAssessment.id.desc())
        .limit(1)
    )


def get_or_create_latest(db: Session, farm: models.Farm) -> models.RiskAssessment:
    row = latest_assessment(db, farm.id)
    return row or run_assessment(db, farm)


def risk_payload(row: models.RiskAssessment) -> dict:
    return {**row.result, "assessment_id": row.id}


def risk_summary(row: models.RiskAssessment | None) -> dict | None:
    if row is None:
        return None
    return {
        "assessment_id": row.id,
        "farm_id": row.farm_id,
        "assessed_at": as_utc(row.assessed_at),
        "overall_score": row.overall_score,
        "overall_level": row.overall_level,
        "overall_label": row.overall_label,
        "stage": row.stage_name,
        "insurance_triggered": row.insurance_triggered,
        "scenario": row.scenario,
    }


def farm_payload(db: Session, farm: models.Farm, today: date | None = None) -> dict:
    today = today or date.today()
    stage = derive_stage(farm.crop, farm.planting_date, today)
    return {
        "id": farm.id,
        "farm_name": farm.name,
        "farmer_name": farm.farmer.name,
        "phone": farm.farmer.phone,
        "language": farm.farmer.language,
        "crop": farm.crop,
        "crop_display": get_crop(farm.crop).display_name,
        "planting_date": farm.planting_date,
        "lat": farm.lat,
        "lon": farm.lon,
        "area_ha": farm.area_ha,
        "county": farm.county,
        "stage": stage.name,
        "days_after_planting": stage.day_after_planting,
        "latest_risk": risk_summary(latest_assessment(db, farm.id)),
    }


def assess_unscored_farms() -> int:
    """Startup helper: score any farm that has never been assessed so listings show a score immediately."""
    n = 0
    with SessionLocal() as db:
        for farm in db.scalars(select(models.Farm).order_by(models.Farm.id)).all():
            if latest_assessment(db, farm.id) is None:
                try:
                    run_assessment(db, farm)
                    n += 1
                except Exception as exc:  # noqa: BLE001 - startup must not fail on one bad farm
                    log.warning("Initial assessment for farm %s failed: %s", farm.id, exc)
    if n:
        log.info("Assessed %d previously unscored farm(s) at startup", n)
    return n
