"""Pydantic request / response models. Every schema carries descriptions + an example
so the auto-generated OpenAPI docs read like a product, not a dump."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.engine.crops import CROP_KEYS

Level = Literal["LOW", "MEDIUM", "HIGH"]
Scenario = Literal["normal", "dry_spell", "heavy_rain"]

# --------------------------------------------------------------------- farms ----


class FarmCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "farmer_name": "Wanjiku Kamau",
                "phone": "+254711000001",
                "language": "sw",
                "farm_name": "Kamau Maize Plot",
                "crop": "maize",
                "planting_date": "2026-07-03",
                "lat": -1.098,
                "lon": 37.012,
                "area_ha": 0.8,
            }
        }
    )

    farmer_name: str = Field(..., min_length=2, max_length=120, description="Farmer's full name")
    phone: str = Field(..., description="Mobile number in E.164 format (+2547...). Used for SMS alerts.")
    language: Literal["en", "sw"] = Field("en", description="Preferred language for advice and SMS")
    farm_name: str = Field(..., min_length=2, max_length=120, description="Human-friendly farm / plot name")
    crop: str = Field(..., description=f"One of: {', '.join(CROP_KEYS)}")
    planting_date: date = Field(..., description="Date the crop was planted / transplanted")
    lat: float = Field(..., ge=-5.5, le=5.5, description="Latitude (Kenya bounds)")
    lon: float = Field(..., ge=33.5, le=42.5, description="Longitude (Kenya bounds)")
    area_ha: float | None = Field(None, gt=0, description="Plot size in hectares (optional)")

    @field_validator("crop")
    @classmethod
    def _crop_known(cls, v: str) -> str:
        from app.engine.crops import get_crop

        return get_crop(v).key

    @field_validator("phone")
    @classmethod
    def _phone_e164(cls, v: str) -> str:
        v = v.strip().replace(" ", "")
        if v.startswith("07") and len(v) == 10:
            v = "+254" + v[1:]
        if not (v.startswith("+") and v[1:].isdigit() and 10 <= len(v) <= 15):
            raise ValueError("phone must be E.164, e.g. +254711000001")
        return v


class RiskSummary(BaseModel):
    """Compact latest-risk view embedded in farm listings."""

    assessment_id: int
    farm_id: int
    assessed_at: datetime
    overall_score: int = Field(..., ge=0, le=100)
    overall_level: Level
    overall_label: str = Field(..., description='e.g. "HIGH CLIMATE RISK"')
    stage: str
    insurance_triggered: bool
    scenario: str | None = None


class FarmOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "farm_name": "Kamau Maize Plot",
                "farmer_name": "Wanjiku Kamau",
                "phone": "+254711000001",
                "language": "sw",
                "crop": "maize",
                "crop_display": "Maize",
                "planting_date": "2026-07-03",
                "lat": -1.098,
                "lon": 37.012,
                "area_ha": 0.8,
                "county": "Kiambu",
                "stage": "flowering",
                "days_after_planting": 62,
                "latest_risk": {
                    "assessment_id": 12,
                    "farm_id": 1,
                    "assessed_at": "2026-09-03T08:00:00Z",
                    "overall_score": 72,
                    "overall_level": "HIGH",
                    "overall_label": "HIGH CLIMATE RISK",
                    "stage": "flowering",
                    "insurance_triggered": True,
                    "scenario": "dry_spell",
                },
            }
        },
    )

    id: int
    farm_name: str
    farmer_name: str
    phone: str
    language: str
    crop: str
    crop_display: str
    planting_date: date
    lat: float
    lon: float
    area_ha: float | None
    county: str | None
    stage: str = Field(..., description="Current growth stage derived from planting date")
    days_after_planting: int
    latest_risk: RiskSummary | None = None


# ------------------------------------------------------------------ weather ----


class WeatherReadingOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "date": "2026-09-03",
                "rainfall_mm": 0.0,
                "temp_max_c": 33.7,
                "temp_min_c": 15.2,
                "temp_mean_c": 24.1,
                "humidity_pct": 38,
                "wind_speed_ms": 3.1,
                "wind_gust_ms": 7.4,
                "heat_index_max_c": 33.2,
                "wbgt_max_c": 27.1,
                "light_index": 0.92,
                "soil_moisture_pct": None,
                "synthetic": False,
            }
        }
    )

    date: date
    rainfall_mm: float = Field(..., description="Daily total from the station rain gauges")
    temp_max_c: float = Field(..., description="Daily max of SHT Temperature")
    temp_min_c: float
    temp_mean_c: float | None = None
    humidity_pct: float = Field(..., description="Daily mean SHT Humidity")
    wind_speed_ms: float | None = Field(None, description="Daily mean wind speed")
    wind_gust_ms: float | None = Field(None, description="Daily max wind speed")
    heat_index_max_c: float | None = Field(None, description="Daily max Heat Index from the station")
    wbgt_max_c: float | None = Field(None, description="Daily max Wet Bulb Globe Temperature from the station")
    light_index: float | None = Field(None, ge=0, le=1, description="SI1145 visible+IR normalised 0-1 (no W/m2 pyranometer)")
    soil_moisture_pct: float | None = Field(None, description="Measured only if a probe exists; the engine models it otherwise")
    synthetic: bool = Field(False, description="True for replayed demo scenarios, False for real station data")


class WeatherHistoryOut(BaseModel):
    farm_id: int
    source: str = Field(..., description="Data source id, e.g. mock:dry_spell or conduit:jkuat")
    days: int
    readings: list[WeatherReadingOut]


# --------------------------------------------------------------------- risk ----


class StageOut(BaseModel):
    name: str = Field(..., description="Growth stage, e.g. flowering")
    day_after_planting: int
    day_in_stage: int
    stage_length_days: int
    progress: float = Field(..., ge=0, le=1, description="0-1 progress through the season")
    water_need_mm_week: float = Field(..., description="FAO-56 crop water requirement for this stage")
    sensitivity: float = Field(..., description="0-1 yield sensitivity to stress in this stage")
    is_critical: bool


class SubScoreOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "score": 81,
                "level": "HIGH",
                "reasons": [
                    "Only 0 mm rain in the last 7 days vs 38 mm/week needed at flowering",
                    "Modelled soil moisture 18% is at the 18% wilting point; ET0 5.1 mm/day",
                    "22 consecutive dry days (<1 mm)",
                ],
            }
        }
    )

    score: int = Field(..., ge=0, le=100, description="0 = no risk, 100 = extreme")
    level: Level
    reasons: list[str] = Field(..., description="Human-readable evidence behind the score")
    label: Literal["GOOD", "FAIR", "POOR"] | None = Field(None, description="Crop health only")


class SubScoresOut(BaseModel):
    drought: SubScoreOut
    flood: SubScoreOut
    heat: SubScoreOut
    crop_health: SubScoreOut


class OverallOut(BaseModel):
    score: int = Field(..., ge=0, le=100)
    level: Level
    label: str = Field(..., description='"LOW CLIMATE RISK" | "MODERATE CLIMATE RISK" | "HIGH CLIMATE RISK"')
    weights: dict[str, float] = Field(..., description="Stage-dependent weights applied to the sub-scores")


class PolicyIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"type": "drought", "window_days": 21, "rainfall_threshold_mm": 30}}
    )

    type: Literal["drought", "excess_rain", "heat"] = Field(..., description="Trigger family")
    window_days: int = Field(..., ge=1, le=120, description="Observation window ending today")
    rainfall_threshold_mm: float | None = Field(
        None, ge=0, description="drought: pay if cumulative rain is below this; excess_rain: pay if any window exceeds it"
    )
    temp_threshold_c: float | None = Field(None, description="heat: a day counts as hot above this max temperature")
    hot_days_threshold: int | None = Field(None, ge=1, description="heat: number of hot days in the window that triggers")
    critical_stages_only: bool = Field(False, description="Only pay out if the crop is in a yield-critical stage")


class InsuranceTriggerOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "triggered": True,
                "rule": "drought_rainfall_deficit",
                "evidence": {
                    "window_days": 21,
                    "rainfall_total_mm": 0.4,
                    "threshold_mm": 30,
                    "deficit_mm": 29.6,
                    "dry_days": 21,
                    "stage": "flowering",
                    "stage_is_critical": True,
                },
                "confidence": 1.0,
                "policy": {"type": "drought", "window_days": 21, "rainfall_threshold_mm": 30, "critical_stages_only": False},
            }
        }
    )

    triggered: bool
    rule: str = Field(..., description="Rule id: drought_rainfall_deficit | excess_rainfall | heat_days")
    evidence: dict[str, Any] = Field(..., description="Observed values behind the decision, for audit")
    confidence: float = Field(..., ge=0, le=1, description="Data completeness x margin from threshold")
    policy: dict[str, Any]


class AdviceOut(BaseModel):
    en: str = Field(..., description="Farmer-friendly advice in English")
    sw: str = Field(..., description="Ushauri kwa Kiswahili")
    source: Literal["gemini", "fallback"] = Field(..., description="gemini when the LLM produced it, fallback for rule-based text")
    sms_en: str = Field(..., description="<=160 char SMS version (EN)")
    sms_sw: str = Field(..., description="<=160 char SMS version (SW)")


class RiskOut(BaseModel):
    """Full Farm Risk Score: the core product of FarmShield."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "assessment_id": 12,
                "farm_id": 1,
                "farm_name": "Kamau Maize Plot",
                "crop": "maize",
                "stage": {
                    "name": "flowering",
                    "day_after_planting": 62,
                    "day_in_stage": 12,
                    "stage_length_days": 25,
                    "progress": 0.496,
                    "water_need_mm_week": 37.8,
                    "sensitivity": 1.0,
                    "is_critical": True,
                },
                "overall": {
                    "score": 72,
                    "level": "HIGH",
                    "label": "HIGH CLIMATE RISK",
                    "weights": {"drought": 0.4, "flood": 0.1, "heat": 0.3, "crop_health": 0.2},
                },
                "sub_scores": {
                    "drought": {"score": 81, "level": "HIGH", "reasons": ["Only 0 mm rain in the last 7 days vs 38 mm/week needed at flowering", "Modelled soil moisture 18% is at the 18% wilting point; ET0 5.1 mm/day"]},
                    "flood": {"score": 0, "level": "LOW", "reasons": ["0 mm in the last 72 h, below the 90 mm flood threshold"]},
                    "heat": {"score": 68, "level": "HIGH", "reasons": ["6 of the last 7 days exceeded 32°C (peak 33.9°C) during flowering"]},
                    "crop_health": {"score": 61, "level": "HIGH", "label": "POOR", "reasons": ["No satellite data: health inferred from weather stress over 30 days"]},
                },
                "insurance_trigger": {
                    "triggered": True,
                    "rule": "drought_rainfall_deficit",
                    "evidence": {"window_days": 21, "rainfall_total_mm": 0.4, "threshold_mm": 30},
                    "confidence": 1.0,
                    "policy": {"type": "drought", "window_days": 21, "rainfall_threshold_mm": 30},
                },
                "advice": {
                    "en": "Your maize is flowering and has had almost no rain for 3 weeks. Irrigate within 24-48 hours if you can. Do not apply fertiliser until rain returns.",
                    "sw": "Mahindi yako yanatoa maua na hayajapata mvua kwa wiki 3. Mwagilia ndani ya saa 24-48 ukiweza. Usiweke mbolea hadi mvua irudi.",
                    "source": "fallback",
                    "sms_en": "FarmShield: Kamau Maize Plot risk HIGH (72/100). Maize flowering, no rain 3 wks. Irrigate in 24-48h. Hold fertiliser.",
                    "sms_sw": "FarmShield: Kamau Maize Plot hatari JUU (72/100). Mahindi yanatoa maua, hakuna mvua wiki 3. Mwagilia ndani ya saa 24-48.",
                },
                "assessed_at": "2026-09-03T08:00:00Z",
                "scenario": "dry_spell",
                "data_sources": ["mock:dry_spell"],
                "readings_used": 30,
                "window_days": 30,
                "ndvi": None,
                "soil_moisture_pct": 18.0,
                "soil_moisture_source": "modelled",
                "et0_mm_day": 5.1,
                "heat_metric": "tmax",
            }
        }
    )

    assessment_id: int
    farm_id: int
    farm_name: str
    crop: str
    stage: StageOut
    overall: OverallOut
    sub_scores: SubScoresOut
    insurance_trigger: InsuranceTriggerOut
    advice: AdviceOut
    assessed_at: datetime
    scenario: str | None = Field(None, description="Mock scenario the readings came from (null for live data)")
    data_sources: list[str]
    readings_used: int
    window_days: int
    ndvi: float | None = Field(None, description="Satellite NDVI if a provider supplied one")
    soil_moisture_pct: float | None = Field(None, description="Latest soil moisture used by the engine (vol. %)")
    soil_moisture_source: Literal["modelled", "measured"] = Field("modelled", description="modelled = Hargreaves ET0 x Kc soil bucket (station has no probe)")
    et0_mm_day: float | None = Field(None, description="Latest reference evapotranspiration (Hargreaves)")
    heat_metric: Literal["wbgt", "heat_index", "tmax"] = Field("tmax", description="Station metric that drove the heat sub-score")


class RiskHistoryItem(BaseModel):
    assessment_id: int
    assessed_at: datetime
    scenario: str | None
    stage: str
    overall_score: int
    overall_level: Level
    drought: int
    flood: int
    heat: int
    crop_health: int
    insurance_triggered: bool


# ----------------------------------------------------------------- scenario ----


class ScenarioOut(BaseModel):
    scenario: Scenario = Field(..., description="Active mock weather scenario")
    provider: str = Field(..., description="Active weather provider (mock | conduit)")
    available: list[str]


class ScenarioUpdate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"scenario": "dry_spell", "reassess": True}})

    scenario: Scenario
    reassess: bool = Field(True, description="Re-run the risk engine for every farm after switching")
    notify: bool = Field(False, description="After re-assessing, send SMS alerts to farmers whose risk change warrants one (dedupe rules apply)")


class ScenarioSwitchOut(BaseModel):
    scenario: Scenario
    reassessed: list[RiskSummary | None] = Field(default_factory=list, description="New summaries per farm (if reassess=true)")
    alerts_sent: list[int] = Field(default_factory=list, description="Alert ids sent when notify=true")


# ------------------------------------------------------------------- errors ----


class ApiError(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"detail": "Farm 42 not found"}})

    detail: str


# ----------------------------------------------------------------- partners ----


class PartnerInfoOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"client": "acme-insurance", "organisation_type": "insurer", "request_count": 42, "last_used_at": "2026-09-03T08:00:00Z"}}
    )

    client: str
    organisation_type: str
    request_count: int
    last_used_at: datetime | None


class BulkSummary(BaseModel):
    high_risk: int
    medium_risk: int
    low_risk: int
    insurance_triggered: int
    mean_score: float | None


class BulkRiskOut(BaseModel):
    count: int = Field(..., description="Number of farms successfully scored")
    summary: BulkSummary = Field(..., description="Portfolio roll-up")
    results: list[RiskOut]
    errors: list[dict[str, Any]] = Field(default_factory=list, description="Per-farm failures (unknown id etc.)")


class TriggerCheckIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "farm_id": 1,
                "policy": {"type": "drought", "window_days": 21, "rainfall_threshold_mm": 30, "critical_stages_only": True},
            }
        }
    )

    farm_id: int
    policy: PolicyIn
    scenario: Scenario | None = Field(None, description="Demo only: evaluate against a mock scenario instead of live data")


class TriggerCheckOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "farm_id": 1,
                "farm_name": "Kamau Maize Plot",
                "crop": "maize",
                "stage": "flowering",
                "triggered": True,
                "rule": "drought_rainfall_deficit",
                "evidence": {
                    "window_days": 21,
                    "window_start": "2026-08-14",
                    "window_end": "2026-09-03",
                    "readings_in_window": 21,
                    "rainfall_total_mm": 0.4,
                    "threshold_mm": 30.0,
                    "deficit_mm": 29.6,
                    "dry_days": 21,
                    "stage_is_critical": True,
                    "stage_gate_blocked": False,
                },
                "confidence": 1.0,
                "policy": {"type": "drought", "window_days": 21, "rainfall_threshold_mm": 30.0, "critical_stages_only": True},
                "assessed_at": "2026-09-03T08:00:00Z",
                "scenario": "dry_spell",
                "data_sources": ["mock:dry_spell"],
            }
        }
    )

    farm_id: int
    farm_name: str
    crop: str
    stage: str
    triggered: bool
    rule: str
    evidence: dict[str, Any]
    confidence: float = Field(..., ge=0, le=1)
    policy: dict[str, Any]
    assessed_at: datetime
    scenario: str | None
    data_sources: list[str]


# ------------------------------------------------------------------- alerts ----


class AlertRequest(BaseModel):
    """Options for previewing / sending an SMS alert. All fields optional."""

    model_config = ConfigDict(json_schema_extra={"example": {"language": "sw", "force": False}})

    language: Literal["en", "sw"] | None = Field(None, description="Override the farmer's preferred language")
    force: bool = Field(False, description="Send even if the dedupe policy says the alert is not warranted (dashboard button)")
    message: str | None = Field(None, max_length=320, description="Custom text instead of the generated SMS (send only; trimmed to 160 chars)")


class AlertPreviewOut(BaseModel):
    """What `POST /farms/{id}/alerts/send` would do right now, without sending."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "farm_id": 1,
                "assessment_id": 12,
                "would_send": True,
                "reason": "level_changed:MEDIUM->HIGH",
                "recipient": "+254711000001",
                "language": "sw",
                "message": "FarmShield: Kamau Maize Plot hatari JUU (72/100). Mahindi kutoa maua. Mwagilia ndani ya saa 24-48. Usiweke mbolea. Bima inaweza kulipa.",
                "chars": 139,
                "level": "HIGH",
                "score": 72,
                "last_alert_id": 3,
                "last_alert_at": "2026-09-03T06:00:00Z",
                "sender": "console",
            }
        }
    )

    farm_id: int
    assessment_id: int
    would_send: bool
    reason: str = Field(
        ...,
        description="forced | first_alert | level_changed:A->B | insurance_trigger | repeat_after_window | duplicate_within_window:Nh | below_alert_threshold:L<M",
    )
    recipient: str
    language: str
    message: str = Field(..., description="Exact SMS text that would be sent")
    chars: int = Field(..., description="Message length (target <= 160 for one SMS segment)")
    level: Level
    score: int
    last_alert_id: int | None = None
    last_alert_at: datetime | None = None
    sender: str = Field(..., description="Configured sender: console | africastalking")


class AlertOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 4,
                "farm_id": 1,
                "assessment_id": 12,
                "channel": "sms",
                "recipient": "+254711000001",
                "language": "sw",
                "message": "FarmShield: Kamau Maize Plot hatari JUU (72/100). Mahindi kutoa maua. Mwagilia ndani ya saa 24-48. Usiweke mbolea.",
                "chars": 118,
                "status": "sent",
                "provider": "console",
                "source": "fallback",
                "trigger_reason": "level_changed:MEDIUM->HIGH",
                "provider_message_id": None,
                "error": "AT_API_KEY not set",
                "created_at": "2026-09-03T08:00:05Z",
            }
        }
    )

    id: int
    farm_id: int
    assessment_id: int | None
    channel: str
    recipient: str
    language: str
    message: str
    chars: int
    status: Literal["sent", "failed", "queued", "previewed"]
    provider: str = Field(..., description="Sender that actually delivered it: console | africastalking")
    source: str = Field(..., description="africastalking | console | fallback (configured gateway failed, console took over)")
    trigger_reason: str | None
    provider_message_id: str | None = None
    error: str | None = Field(None, description="Gateway error if the configured sender failed")
    created_at: datetime


class AlertSendOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "farm_id": 1,
                "sent": False,
                "reason": "duplicate_within_window:6h",
                "alert": None,
            }
        }
    )

    farm_id: int
    sent: bool = Field(..., description="False when the dedupe policy suppressed the SMS (HTTP still 200)")
    reason: str
    alert: AlertOut | None = Field(None, description="The recorded alert when sent")
