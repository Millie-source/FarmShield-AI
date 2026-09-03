"""Crop calendars and agronomic thresholds - ALL scoring constants live here as data.

Agronomic basis (cite these to judges / underwriters):

* FAO Irrigation & Drainage Paper 56 (Allen et al., 1998) - crop coefficients (Kc)
  per growth stage and stage lengths, Tables 11 & 12.  Water need per stage is
  ETc = Kc * ETo.  For Juja / Thika (1,500 m, semi-humid) a long-term mean
  reference evapotranspiration ETo ~ 4.5 mm/day is used
  (FAO CLIMWAT/CROPWAT station "Thika"), so weekly need = Kc * 4.5 * 7.
* KALRO / Kenya Ministry of Agriculture maize production guides - medium-maturity
  hybrids (H513, H614) in central Kenya: ~120-130 days; tasselling/silking
  50-75 DAP is the yield-critical window; > 35 C at silking reduces pollen viability.
* KALRO common bean guide (GLP-2 Rose Coco, KAT B1): 85-95 days, flowering
  35-55 DAP, heat > 30 C at flowering causes flower abortion.
* FAO "Crop Water Information" sheets (potato, tomato, cabbage/brassica) for
  temperature optima, drought sensitivity by stage and waterlogging tolerance.
* Soil thresholds are volumetric water content (%) typical of the red
  clay-loam nitisols around Juja: permanent wilting point ~ 15-20 %,
  field capacity ~ 35-40 %, saturation ~ 45 %.

Sensitivity weights (0-1) express how much yield loss a stress episode causes
in that stage - flowering / grain-fill are the most sensitive (FAO-33 yield
response factor Ky is highest at flowering for maize and beans).
"""
from __future__ import annotations

from dataclasses import dataclass

ETO_MM_DAY = 4.5  # long-term mean reference ET for Juja/Thika, FAO CLIMWAT


@dataclass(frozen=True)
class StageSpec:
    name: str
    days: int  # length of this stage
    kc: float  # FAO-56 crop coefficient (mid-stage value)
    sensitivity: float  # 0-1 yield sensitivity to water/heat stress
    waterlogging_sensitivity: float  # 0-1 sensitivity to saturated soil / flooding

    @property
    def water_need_mm_week(self) -> float:
        return round(self.kc * ETO_MM_DAY * 7, 1)


@dataclass(frozen=True)
class CropSpec:
    key: str
    display_name: str
    stages: tuple[StageSpec, ...]
    max_temp_c: float  # daily max above which heat stress accumulates
    flowering_max_temp_c: float  # tighter limit in the most sensitive stage
    wilting_soil_pct: float  # below this: severe water stress
    stress_soil_pct: float  # below this: onset of stress
    saturation_soil_pct: float  # above this: waterlogging risk
    heavy_rain_24h_mm: float  # 24 h total considered a heavy-rain event
    heavy_rain_72h_mm: float  # 72 h total considered a flood-risk event

    @property
    def season_length_days(self) -> int:
        return sum(s.days for s in self.stages)


CROPS: dict[str, CropSpec] = {
    # Medium-maturity hybrid maize, central Kenya highlands (KALRO). FAO-56 Kc: 0.3 / 0.7 / 1.2 / 1.2 / 0.6
    "maize": CropSpec(
        key="maize",
        display_name="Maize",
        stages=(
            StageSpec("establishment", 20, 0.30, 0.50, 0.70),  # emergence; rot risk if waterlogged
            StageSpec("vegetative", 30, 0.70, 0.60, 0.50),
            StageSpec("flowering", 25, 1.20, 1.00, 0.40),  # tasselling + silking, most critical
            StageSpec("grain_fill", 30, 1.15, 0.85, 0.30),
            StageSpec("maturity", 20, 0.60, 0.30, 0.20),
        ),
        max_temp_c=35.0,
        flowering_max_temp_c=32.0,
        wilting_soil_pct=18.0,
        stress_soil_pct=26.0,
        saturation_soil_pct=42.0,
        heavy_rain_24h_mm=40.0,
        heavy_rain_72h_mm=90.0,
    ),
    # Common bean (Rose Coco / KAT B1), ~90 days. FAO-56 Kc: 0.4 / 0.8 / 1.15 / 1.1 / 0.35
    "beans": CropSpec(
        key="beans",
        display_name="Beans",
        stages=(
            StageSpec("establishment", 15, 0.40, 0.50, 0.80),
            StageSpec("vegetative", 20, 0.80, 0.65, 0.60),
            StageSpec("flowering", 20, 1.15, 1.00, 0.50),
            StageSpec("pod_fill", 20, 1.10, 0.85, 0.40),
            StageSpec("maturity", 15, 0.35, 0.25, 0.30),
        ),
        max_temp_c=32.0,
        flowering_max_temp_c=30.0,
        wilting_soil_pct=18.0,
        stress_soil_pct=25.0,
        saturation_soil_pct=40.0,
        heavy_rain_24h_mm=35.0,
        heavy_rain_72h_mm=80.0,
    ),
    # Potato (Shangi / Dutch Robijn), ~110 days. FAO-56 Kc: 0.5 / 0.8 / 1.15 / 1.15 / 0.75
    "potatoes": CropSpec(
        key="potatoes",
        display_name="Potatoes",
        stages=(
            StageSpec("establishment", 25, 0.50, 0.40, 0.80),
            StageSpec("vegetative", 25, 0.80, 0.60, 0.60),
            StageSpec("tuber_initiation", 15, 1.15, 1.00, 0.60),
            StageSpec("tuber_bulking", 30, 1.15, 0.90, 0.60),  # waterlogging -> tuber rot
            StageSpec("maturity", 15, 0.75, 0.30, 0.40),
        ),
        max_temp_c=30.0,
        flowering_max_temp_c=27.0,  # tuberisation stops above ~27-30 C
        wilting_soil_pct=20.0,
        stress_soil_pct=28.0,
        saturation_soil_pct=40.0,
        heavy_rain_24h_mm=35.0,
        heavy_rain_72h_mm=80.0,
    ),
    # Tomato (transplanted), ~110 days. FAO-56 Kc: 0.6 / 0.9 / 1.15 / 1.15 / 0.8
    "tomatoes": CropSpec(
        key="tomatoes",
        display_name="Tomatoes",
        stages=(
            StageSpec("establishment", 20, 0.60, 0.50, 0.70),
            StageSpec("vegetative", 25, 0.90, 0.60, 0.50),
            StageSpec("flowering", 25, 1.15, 1.00, 0.50),  # fruit set fails > 32 C
            StageSpec("fruit_fill", 25, 1.15, 0.85, 0.60),  # cracking / blight in heavy rain
            StageSpec("ripening", 15, 0.80, 0.40, 0.50),
        ),
        max_temp_c=34.0,
        flowering_max_temp_c=32.0,
        wilting_soil_pct=20.0,
        stress_soil_pct=28.0,
        saturation_soil_pct=42.0,
        heavy_rain_24h_mm=35.0,
        heavy_rain_72h_mm=80.0,
    ),
    # Kale / sukuma wiki (Brassica oleracea var. acephala), continuous harvest from ~40 DAP.
    # FAO-56 (cabbage family) Kc: 0.7 / 1.0 / 1.05
    "kale": CropSpec(
        key="kale",
        display_name="Kale (Sukuma wiki)",
        stages=(
            StageSpec("establishment", 14, 0.70, 0.50, 0.60),
            StageSpec("vegetative", 26, 1.00, 0.60, 0.50),
            StageSpec("leaf_harvest", 40, 1.05, 0.55, 0.40),
        ),
        max_temp_c=30.0,
        flowering_max_temp_c=30.0,  # no flowering stage; same threshold
        wilting_soil_pct=20.0,
        stress_soil_pct=28.0,
        saturation_soil_pct=42.0,
        heavy_rain_24h_mm=40.0,
        heavy_rain_72h_mm=90.0,
    ),
}

CROP_KEYS: tuple[str, ...] = tuple(CROPS.keys())

# ---- Scoring constants (shared across crops) -------------------------------

DRY_DAY_MM = 1.0  # a day with < 1 mm is a "dry day" (WMO convention)
LOW_HUMIDITY_PCT = 40.0  # below this, evaporative demand amplifies heat stress
HIGH_HUMIDITY_PCT = 85.0  # above this with heat -> fungal disease pressure

# Overall-score weights by stage class.  Drought and heat dominate in critical
# (flowering / grain-fill) stages; flood / waterlogging dominates at
# establishment; crop health is always a steady 20 %.
OVERALL_WEIGHTS: dict[str, dict[str, float]] = {
    "critical": {"drought": 0.40, "flood": 0.10, "heat": 0.30, "crop_health": 0.20},
    "establishment": {"drought": 0.30, "flood": 0.30, "heat": 0.20, "crop_health": 0.20},
    "default": {"drought": 0.35, "flood": 0.20, "heat": 0.25, "crop_health": 0.20},
}
# Overall = max(weighted mean, WORST_HAZARD_FLOOR * worst sub-score).
# A single HIGH hazard must not be averaged away by three LOW ones: the overall
# score never sits more than 15 % below the dominant hazard.
WORST_HAZARD_FLOOR = 0.85

OVERALL_LABELS: dict[str, str] = {
    "LOW": "LOW CLIMATE RISK",
    "MEDIUM": "MODERATE CLIMATE RISK",
    "HIGH": "HIGH CLIMATE RISK",
}

_ALIASES = {
    "sukuma": "kale",
    "sukuma_wiki": "kale",
    "sukuma wiki": "kale",
    "potato": "potatoes",
    "tomato": "tomatoes",
    "bean": "beans",
}


def get_crop(key: str) -> CropSpec:
    k = key.strip().lower()
    k = _ALIASES.get(k, k)
    if k not in CROPS:
        raise ValueError(f"Unknown crop '{key}'. Supported: {', '.join(CROP_KEYS)}")
    return CROPS[k]
