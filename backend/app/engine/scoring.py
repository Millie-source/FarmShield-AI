"""Rule-based, explainable Farm Risk Score.

``assess(readings, crop, stage, ndvi)`` -> ``RiskAssessment`` with four sub-scores
(drought, flood, heat, crop_health) and a weighted overall score.  Every point
awarded is accompanied by a human-readable reason so an insurer can audit why a
farm scored 72.  All thresholds come from ``crops.py``; nothing here is a magic
number without a name.

Scoring philosophy
------------------
* Each hazard sub-score is built additively from independent pieces of evidence
  (e.g. 7-day rainfall deficit, soil moisture, dry-day run), each capped, then
  scaled by the stage sensitivity weight - a dry week hurts flowering maize far
  more than maturing maize (FAO-33 yield-response factors).
* Only readings since planting count towards crop stress: rain that fell before
  a seed was in the ground did not stress the plant - but the soil-water bucket
  is run over the whole history so soil moisture *at* planting is realistic.
* The station has no soil probe: soil moisture is **modelled** (water_balance.py)
  and every reason that uses it says so.  Heat stress prefers the station's WBGT
  / Heat Index maxima and falls back to Tmax.
* The overall score is a stage-weighted mean, floored at a fraction of the worst
  hazard so a single HIGH risk is never averaged away by three LOW ones.
"""
from __future__ import annotations

from datetime import timedelta
from statistics import mean

from .crops import (
    DRY_DAY_MM,
    HIGH_HUMIDITY_PCT,
    LOW_HUMIDITY_PCT,
    OVERALL_LABELS,
    OVERALL_WEIGHTS,
    WBGT_PER_TMAX_DEGREE,
    WORST_HAZARD_FLOOR,
    CropSpec,
    get_crop,
)
from .types import Overall, Reading, RiskAssessment, Stage, SubScore, level_for
from .water_balance import DayBalance, simulate

# Maximum points each evidence component can contribute (before stage scaling).
DROUGHT_PTS = {"short_deficit": 40, "long_deficit": 25, "soil": 25, "dry_run": 10}
FLOOD_PTS = {"rain_24h": 45, "rain_72h": 45, "soil": 15, "trend": 10}
HEAT_PTS = {"hot_day": 12, "hot_days_cap": 60, "long_hot_day": 1.5, "long_cap": 15, "excess": 15, "humidity": 10}
HEAT_METRIC_LABELS = {"wbgt": "WBGT", "heat_index": "heat index", "tmax": "max temperature"}
HEALTH_STRESS_WEIGHTS = {"drought": 0.55, "heat": 0.30, "flood": 0.15}
NDVI_GOOD = 0.60  # dense, healthy canopy (typical vigorous maize/beans mid-season)
NDVI_POOR = 0.35  # sparse / stressed canopy
LONG_WINDOW_MIN_DAYS = 10  # need at least this much history to score cumulative deficit


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _pretty(stage_name: str) -> str:
    return stage_name.replace("_", " ")


def _stage_multiplier(sensitivity: float) -> float:
    """0.7 (insensitive stage) .. 1.2 (yield-critical stage)."""
    return 0.7 + 0.5 * sensitivity


def _last_days(readings: list[Reading], days: int) -> list[Reading]:
    end = readings[-1].date
    start = end - timedelta(days=days - 1)
    return [r for r in readings if r.date >= start]


def _rain(readings: list[Reading]) -> float:
    return sum(r.rainfall_mm for r in readings)


def _consecutive_dry_days(readings: list[Reading]) -> int:
    n = 0
    for r in reversed(readings):
        if r.rainfall_mm < DRY_DAY_MM:
            n += 1
        else:
            break
    return n


# ----------------------------------------------------------------- drought ----
def score_drought(readings: list[Reading], spec: CropSpec, stage: Stage, soil_today: DayBalance | None = None) -> SubScore:
    reasons: list[str] = []
    raw = 0.0
    latest = readings[-1]
    span_days = (latest.date - readings[0].date).days + 1
    need_week = stage.water_need_mm_week
    stage_txt = _pretty(stage.name)

    # 1. Short-term deficit: last 7 days (or since planting if younger), vs. stage need.
    short = _last_days(readings, 7)
    short_days = (latest.date - short[0].date).days + 1
    short_rain = _rain(short)
    weekly_equiv = short_rain * 7 / short_days if short_days < 7 else short_rain
    deficit = _clamp(1 - weekly_equiv / need_week, 0, 1) if need_week > 0 else 0.0
    raw += DROUGHT_PTS["short_deficit"] * deficit
    window_txt = f"last {short_days} days" if short_days >= 7 else f"{short_days} days since planting"
    if deficit > 0.15:
        reasons.append(
            f"Only {short_rain:.0f} mm rain in the {window_txt} vs {need_week:.0f} mm/week needed at {stage_txt}"
        )
    else:
        reasons.append(f"{short_rain:.0f} mm rain in the {window_txt} meets the {need_week:.0f} mm/week need at {stage_txt}")

    # 2. Cumulative deficit over the available history (max 30 days, only since planting).
    if span_days >= LONG_WINDOW_MIN_DAYS:
        long_rain = _rain(readings)
        long_need = need_week * span_days / 7
        long_deficit = _clamp(1 - long_rain / long_need, 0, 1) if long_need > 0 else 0.0
        raw += DROUGHT_PTS["long_deficit"] * long_deficit
        if long_deficit > 0.3:
            reasons.append(
                f"{long_rain:.0f} mm over the last {span_days} days vs ~{long_need:.0f} mm crop requirement "
                f"({long_deficit * 100:.0f}% cumulative deficit)"
            )
    else:
        reasons.append(f"Planted {stage.day_after_planting} days ago: cumulative deficit not yet assessed")

    # 3. Soil moisture (modelled water balance unless a probe value exists) vs. wilting / stress thresholds.
    if soil_today is not None:
        soil = soil_today.soil_moisture_pct
        src = "Measured" if soil_today.measured else "Modelled"
        et_txt = f"; ET0 {soil_today.et0_mm:.1f} mm/day" if not soil_today.measured else ""
        if soil < spec.wilting_soil_pct + 0.5:
            raw += DROUGHT_PTS["soil"]
            reasons.append(f"{src} soil moisture {soil:.0f}% is at the {spec.wilting_soil_pct:.0f}% wilting point{et_txt}")
        elif soil < spec.stress_soil_pct:
            frac = (spec.stress_soil_pct - soil) / (spec.stress_soil_pct - spec.wilting_soil_pct)
            raw += DROUGHT_PTS["soil"] * 0.6 * frac
            reasons.append(f"{src} soil moisture {soil:.0f}% is below the {spec.stress_soil_pct:.0f}% stress threshold{et_txt}")
        else:
            reasons.append(f"{src} soil moisture {soil:.0f}% is above the {spec.stress_soil_pct:.0f}% stress threshold{et_txt}")

    # 4. Consecutive dry days.
    cdd = _consecutive_dry_days(readings)
    if cdd >= 14:
        raw += DROUGHT_PTS["dry_run"]
    elif cdd >= 7:
        raw += DROUGHT_PTS["dry_run"] * 0.7
    elif cdd >= 4:
        raw += DROUGHT_PTS["dry_run"] * 0.3
    if cdd >= 4:
        reasons.append(f"{cdd} consecutive dry days (<{DRY_DAY_MM:.0f} mm)")

    mult = _stage_multiplier(stage.sensitivity)
    if stage.is_critical and raw > 10:
        reasons.append(f"{stage_txt.capitalize()} is a yield-critical stage: water stress weighted x{mult:.2f}")
    score = int(round(_clamp(raw * mult)))
    return SubScore(score=score, level=level_for(score), reasons=reasons)


# ------------------------------------------------------------------- flood ----
def score_flood(readings: list[Reading], spec: CropSpec, stage: Stage, soil_today: DayBalance | None = None) -> SubScore:
    reasons: list[str] = []
    raw = 0.0
    latest = readings[-1]
    r24 = latest.rainfall_mm
    last3 = _last_days(readings, 3)
    r72 = _rain(last3)

    ratio24 = r24 / spec.heavy_rain_24h_mm
    raw += min(FLOOD_PTS["rain_24h"], 35 * ratio24)
    ratio72 = r72 / spec.heavy_rain_72h_mm
    raw += min(FLOOD_PTS["rain_72h"], 35 * ratio72)
    if ratio24 >= 0.5 or ratio72 >= 0.5:
        reasons.append(
            f"{r24:.0f} mm in the last 24 h and {r72:.0f} mm in 72 h "
            f"(heavy-rain thresholds {spec.heavy_rain_24h_mm:.0f} / {spec.heavy_rain_72h_mm:.0f} mm)"
        )
    else:
        reasons.append(f"{r72:.0f} mm in the last 72 h, below the {spec.heavy_rain_72h_mm:.0f} mm flood threshold")

    if soil_today is not None:
        soil = soil_today.soil_moisture_pct
        src = "Measured" if soil_today.measured else "Modelled"
        field_capacity = spec.saturation_soil_pct - 6
        if soil >= spec.saturation_soil_pct - 0.5:
            raw += FLOOD_PTS["soil"]
            reasons.append(f"{src} soil moisture {soil:.0f}% is at saturation ({spec.saturation_soil_pct:.0f}%): waterlogging risk")
        elif soil >= field_capacity:
            raw += FLOOD_PTS["soil"] * 0.5
            reasons.append(f"{src} soil moisture {soil:.0f}% is near field capacity; little buffer for more rain")
        if soil_today.runoff_mm > 0:
            reasons.append(f"{soil_today.runoff_mm:.0f} mm of today's rain could not infiltrate the saturated soil (modelled runoff)")

    if len(readings) >= 7:
        prev4 = [r for r in _last_days(readings, 7) if r not in last3]
        if prev4:
            recent_mean = mean(r.rainfall_mm for r in last3)
            prev_mean = mean(r.rainfall_mm for r in prev4)
            if recent_mean > 2 * max(prev_mean, 1.0) and r72 >= 0.5 * spec.heavy_rain_72h_mm:
                raw += FLOOD_PTS["trend"]
                reasons.append("Rainfall is intensifying: last 3 days averaged more than double the previous 4")

    wl = spec.stages[stage.index].waterlogging_sensitivity
    mult = _stage_multiplier(wl)
    if wl >= 0.6 and raw > 10:
        reasons.append(f"{_pretty(stage.name).capitalize()} stage is sensitive to waterlogging: weighted x{mult:.2f}")
    score = int(round(_clamp(raw * mult)))
    return SubScore(score=score, level=level_for(score), reasons=reasons)


# -------------------------------------------------------------------- heat ----
def _heat_thresholds(spec: CropSpec, stage: Stage) -> dict[str, float]:
    """Per-metric hot-day limits for this stage. The flowering tightening (max_temp_c -
    flowering_max_temp_c) is applied 1:1 to Heat Index and scaled into WBGT space."""
    offset = spec.max_temp_c - stage.max_temp_c
    return {
        "wbgt": spec.wbgt_max_c - offset * WBGT_PER_TMAX_DEGREE,
        "heat_index": spec.heat_index_max_c - offset,
        "tmax": stage.max_temp_c,
    }


def _exceedance(r: Reading, thr: dict[str, float]) -> tuple[str, float]:
    """(metric, degrees above its limit) for the metric that exceeds its limit the most.
    WBGT and Heat Index are read straight from the station when present; Tmax always counts."""
    cands = {"tmax": r.temp_max_c - thr["tmax"]}
    if r.wbgt_max_c is not None:
        cands["wbgt"] = r.wbgt_max_c - thr["wbgt"]
    if r.heat_index_max_c is not None:
        cands["heat_index"] = r.heat_index_max_c - thr["heat_index"]
    m = max(cands, key=cands.get)  # type: ignore[arg-type]
    return m, cands[m]


def score_heat(readings: list[Reading], spec: CropSpec, stage: Stage) -> tuple[SubScore, str]:
    """Heat sub-score plus the station metric that drove it (wbgt | heat_index | tmax)."""
    reasons: list[str] = []
    raw = 0.0
    thr = _heat_thresholds(spec, stage)
    short = _last_days(readings, 7)
    ex_short = [_exceedance(r, thr) for r in short]
    ex_all = [_exceedance(r, thr) for r in readings]
    hot_short = [(m, e) for m, e in ex_short if e > 0]
    hot_all = [(m, e) for m, e in ex_all if e > 0]
    stage_txt = _pretty(stage.name)

    raw += min(HEAT_PTS["hot_days_cap"], HEAT_PTS["hot_day"] * len(hot_short))
    extra_long = max(0, len(hot_all) - len(hot_short))
    raw += min(HEAT_PTS["long_cap"], HEAT_PTS["long_hot_day"] * extra_long)

    driver = "tmax"
    if hot_short:
        counts: dict[str, int] = {}
        for m, _ in hot_short:
            counts[m] = counts.get(m, 0) + 1
        driver = max(counts, key=counts.get)  # type: ignore[arg-type]
        excess = mean(e for _, e in hot_short)
        raw += min(HEAT_PTS["excess"], excess * 5)
        peak_m, peak_e = max(hot_short, key=lambda x: x[1])
        reasons.append(
            f"{len(hot_short)} of the last {len(short)} days exceeded the crop heat limit during {stage_txt} "
            f"(worst: {HEAT_METRIC_LABELS[peak_m]} {thr[peak_m] + peak_e:.1f}°C vs {thr[peak_m]:.0f}°C limit)"
        )
        if driver != "tmax":
            reasons.append(f"Humid heat: read from the station's {HEAT_METRIC_LABELS[driver]} maxima (Tmax peak {max(r.temp_max_c for r in short):.1f}°C)")
    else:
        peak = max(r.temp_max_c for r in short)
        metrics = " / ".join(HEAT_METRIC_LABELS[m] for m in ("wbgt", "heat_index", "tmax") if m == "tmax" or any(getattr(r, m + "_max_c") is not None for r in short))
        reasons.append(f"No days above the {thr['tmax']:.0f}°C {stage_txt} limit in the last {len(short)} days (Tmax peak {peak:.1f}°C; checked {metrics})")
    if extra_long:
        reasons.append(f"{len(hot_all)} hot days in the last {len(readings)} readings")

    rh = mean(r.humidity_pct for r in short)
    if rh < LOW_HUMIDITY_PCT and (hot_short or raw > 0):
        raw += HEAT_PTS["humidity"]
        reasons.append(f"Low humidity ({rh:.0f}%) increases evaporative demand and heat stress")
    elif rh > HIGH_HUMIDITY_PCT and hot_short:
        raw += HEAT_PTS["humidity"] * 0.5
        reasons.append(f"High humidity ({rh:.0f}%) with heat raises fungal disease pressure")

    mult = _stage_multiplier(stage.sensitivity)
    if stage.is_critical and hot_short:
        reasons.append(f"Heat during {stage_txt} directly reduces yield: weighted x{mult:.2f}")
    score = int(round(_clamp(raw * mult)))
    return SubScore(score=score, level=level_for(score), reasons=reasons), driver


# ------------------------------------------------------------- crop health ----
def _health_label(score: float) -> str:
    lvl = level_for(score)
    return {"LOW": "GOOD", "MEDIUM": "FAIR", "HIGH": "POOR"}[lvl]


def score_crop_health(
    readings: list[Reading],
    stage: Stage,
    drought: SubScore,
    flood: SubScore,
    heat: SubScore,
    ndvi: float | None,
) -> SubScore:
    reasons: list[str] = []
    stage_txt = _pretty(stage.name)
    if ndvi is not None:
        # Linear map: NDVI >= NDVI_GOOD -> 0 risk, <= NDVI_POOR -> 100 risk.
        frac = _clamp((NDVI_GOOD - ndvi) / (NDVI_GOOD - NDVI_POOR), 0, 1)
        score = int(round(frac * 100))
        canopy = "dense, healthy" if ndvi >= NDVI_GOOD else "moderate" if ndvi >= NDVI_POOR else "sparse or stressed"
        reasons.append(f"Satellite NDVI {ndvi:.2f} indicates a {canopy} canopy at {stage_txt}")
    else:
        stress = (
            HEALTH_STRESS_WEIGHTS["drought"] * drought.score
            + HEALTH_STRESS_WEIGHTS["heat"] * heat.score
            + HEALTH_STRESS_WEIGHTS["flood"] * flood.score
        )
        # Damage accumulates: a crop in the ground for 5 days has had little time to suffer.
        exposure = 0.6 + 0.4 * min(1.0, stage.day_after_planting / 30)
        score = int(round(_clamp(stress * exposure)))
        reasons.append(
            f"No satellite data: health inferred from weather stress over {len(readings)} days "
            f"(drought {drought.score}, heat {heat.score}, flood {flood.score})"
        )
        if stage.day_after_planting < 30:
            reasons.append(f"Crop is only {stage.day_after_planting} days old: limited accumulated stress")
    label = _health_label(score)
    reasons.append(f"Crop condition rated {label} at {stage_txt} (day {stage.day_in_stage + 1} of {stage.stage_length_days})")
    return SubScore(score=score, level=level_for(score), reasons=reasons, label=label)  # type: ignore[arg-type]


# ----------------------------------------------------------------- overall ----
def _weights_for(stage: Stage) -> dict[str, float]:
    if stage.is_critical:
        return dict(OVERALL_WEIGHTS["critical"])
    if stage.index == 0:
        return dict(OVERALL_WEIGHTS["establishment"])
    return dict(OVERALL_WEIGHTS["default"])


def score_overall(subs: dict[str, SubScore], stage: Stage) -> Overall:
    weights = _weights_for(stage)
    weighted = sum(subs[k].score * w for k, w in weights.items())
    worst = max(s.score for s in subs.values())
    score = int(round(_clamp(max(weighted, WORST_HAZARD_FLOOR * worst))))
    level = level_for(score)
    return Overall(score=score, level=level, label=OVERALL_LABELS[level], weights=weights)


# ------------------------------------------------------------------ assess ----
def assess(readings: list[Reading], crop: str, stage: Stage, ndvi: float | None = None) -> RiskAssessment:
    """Score a farm from its weather history, crop and current growth stage."""
    if not readings:
        raise ValueError("assess() needs at least one weather reading")
    spec = get_crop(crop)
    ordered = sorted(readings, key=lambda r: r.date)
    # Only weather since planting stresses the crop (keep >= 1 reading).
    planting = ordered[-1].date - timedelta(days=stage.day_after_planting)
    since_planting = [r for r in ordered if r.date >= planting] or ordered[-1:]
    window = _last_days(since_planting, 30)

    # Soil-water bucket over the *whole* history (pre-planting rain sets the starting moisture).
    balance = simulate(ordered, spec, planting)
    soil_today = balance[-1]

    drought = score_drought(window, spec, stage, soil_today)
    flood = score_flood(window, spec, stage, soil_today)
    heat, heat_metric = score_heat(window, spec, stage)
    health = score_crop_health(window, stage, drought, flood, heat, ndvi)
    subs = {"drought": drought, "flood": flood, "heat": heat, "crop_health": health}
    overall = score_overall(subs, stage)
    return RiskAssessment(
        crop=spec.key,
        stage=stage,
        drought=drought,
        flood=flood,
        heat=heat,
        crop_health=health,
        overall=overall,
        readings_used=len(window),
        window_days=(window[-1].date - window[0].date).days + 1,
        ndvi=ndvi,
        soil_moisture_pct=soil_today.soil_moisture_pct,
        soil_moisture_source="measured" if soil_today.measured else "modelled",
        et0_mm_day=soil_today.et0_mm,
        heat_metric=heat_metric,
    )
