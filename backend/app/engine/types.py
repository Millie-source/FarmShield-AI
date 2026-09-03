"""Plain data contracts for the FarmShield risk engine.

Everything in ``engine/`` is stdlib-only: no FastAPI, no SQLAlchemy, no network.
The backend imports these types; nothing here imports from outside ``engine/``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal

Level = Literal["LOW", "MEDIUM", "HIGH"]
HealthLabel = Literal["GOOD", "FAIR", "POOR"]

# Score -> level bands, shared by every sub-score and the overall score.
LEVEL_MEDIUM_FROM = 30
LEVEL_HIGH_FROM = 60


def level_for(score: float) -> Level:
    if score >= LEVEL_HIGH_FROM:
        return "HIGH"
    if score >= LEVEL_MEDIUM_FROM:
        return "MEDIUM"
    return "LOW"


@dataclass(frozen=True)
class Reading:
    """One day of weather-station observations for a location."""

    date: date
    rainfall_mm: float
    temp_max_c: float
    temp_min_c: float
    humidity_pct: float
    soil_moisture_pct: float  # volumetric water content, 0-100
    solar_radiation_wm2: float | None = None
    wind_speed_ms: float | None = None

    @property
    def temp_mean_c(self) -> float:
        return (self.temp_max_c + self.temp_min_c) / 2


@dataclass(frozen=True)
class Stage:
    """Current growth stage of a crop derived from planting date."""

    crop: str
    name: str
    day_after_planting: int  # days since planting (0 = planting day)
    day_in_stage: int
    stage_length_days: int
    season_length_days: int
    water_need_mm_week: float  # stage-specific crop water requirement
    sensitivity: float  # 0-1 stress sensitivity weight for this stage
    max_temp_c: float  # crop heat-stress threshold (daily max)
    index: int  # 0-based position in the crop calendar

    @property
    def progress(self) -> float:
        """0-1 progress through the whole season."""
        return min(1.0, self.day_after_planting / self.season_length_days)

    @property
    def is_critical(self) -> bool:
        return self.sensitivity >= 0.8


@dataclass
class SubScore:
    score: int  # 0-100, higher = more risk
    level: Level
    reasons: list[str] = field(default_factory=list)
    label: HealthLabel | None = None  # only used by crop_health (GOOD / FAIR / POOR)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"score": self.score, "level": self.level, "reasons": list(self.reasons)}
        if self.label is not None:
            d["label"] = self.label
        return d


@dataclass
class Overall:
    score: int
    level: Level
    label: str  # e.g. "HIGH CLIMATE RISK"
    weights: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "level": self.level, "label": self.label, "weights": dict(self.weights)}


@dataclass
class RiskAssessment:
    crop: str
    stage: Stage
    drought: SubScore
    flood: SubScore
    heat: SubScore
    crop_health: SubScore
    overall: Overall
    readings_used: int
    window_days: int
    ndvi: float | None = None

    @property
    def sub_scores(self) -> dict[str, SubScore]:
        return {
            "drought": self.drought,
            "flood": self.flood,
            "heat": self.heat,
            "crop_health": self.crop_health,
        }

    @property
    def all_reasons(self) -> list[str]:
        out: list[str] = []
        for s in self.sub_scores.values():
            out.extend(s.reasons)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "crop": self.crop,
            "stage": {
                "name": self.stage.name,
                "day_after_planting": self.stage.day_after_planting,
                "day_in_stage": self.stage.day_in_stage,
                "stage_length_days": self.stage.stage_length_days,
                "progress": round(self.stage.progress, 3),
                "water_need_mm_week": self.stage.water_need_mm_week,
                "sensitivity": self.stage.sensitivity,
                "is_critical": self.stage.is_critical,
            },
            "sub_scores": {k: v.to_dict() for k, v in self.sub_scores.items()},
            "overall": self.overall.to_dict(),
            "readings_used": self.readings_used,
            "window_days": self.window_days,
            "ndvi": self.ndvi,
        }


PolicyType = Literal["drought", "excess_rain", "heat"]


@dataclass(frozen=True)
class Policy:
    """Parametric policy definition supplied by an insurer / SACCO."""

    type: PolicyType
    window_days: int
    rainfall_threshold_mm: float | None = None  # drought: min cumulative rain; excess_rain: max
    temp_threshold_c: float | None = None  # heat: daily max above which a day counts
    hot_days_threshold: int | None = None  # heat: number of hot days in window that triggers
    critical_stages_only: bool = False  # only pay out if crop is in a critical stage

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class TriggerResult:
    triggered: bool
    rule: str
    evidence: dict[str, Any]
    confidence: float  # 0-1: how sure we are the trigger state is correct
    policy: Policy

    def to_dict(self) -> dict[str, Any]:
        return {
            "triggered": self.triggered,
            "rule": self.rule,
            "evidence": self.evidence,
            "confidence": round(self.confidence, 2),
            "policy": self.policy.to_dict(),
        }
