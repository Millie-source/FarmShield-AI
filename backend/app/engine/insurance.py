"""Parametric insurance trigger rules.

``check_trigger(readings, crop, stage, policy)`` evaluates one policy against the
observed weather and returns ``TriggerResult`` with the evidence an underwriter
needs to audit the decision.  Three rule families:

* ``drought``      - cumulative rainfall over ``window_days`` below ``rainfall_threshold_mm``
* ``excess_rain``  - any rolling ``window_days`` total above ``rainfall_threshold_mm``
* ``heat``         - at least ``hot_days_threshold`` days above ``temp_threshold_c`` in the window

``critical_stages_only`` gates payouts to yield-critical growth stages (a dry
window while maize is at maturity does little damage; the same window at
silking is a crop failure).

Confidence blends data completeness (readings available vs. window length) and
the margin by which the observation clears / misses the threshold.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from .crops import DRY_DAY_MM, get_crop
from .types import Policy, Reading, Stage, TriggerResult

RULE_NAMES = {"drought": "drought_rainfall_deficit", "excess_rain": "excess_rainfall", "heat": "heat_days"}


def _validate(policy: Policy) -> None:
    if policy.window_days <= 0:
        raise ValueError("policy.window_days must be positive")
    if policy.type in ("drought", "excess_rain") and policy.rainfall_threshold_mm is None:
        raise ValueError(f"policy type '{policy.type}' requires rainfall_threshold_mm")
    if policy.type == "heat" and (policy.temp_threshold_c is None or policy.hot_days_threshold is None):
        raise ValueError("policy type 'heat' requires temp_threshold_c and hot_days_threshold")
    if policy.type not in RULE_NAMES:
        raise ValueError(f"Unknown policy type '{policy.type}'")


def _window(readings: list[Reading], days: int) -> list[Reading]:
    ordered = sorted(readings, key=lambda r: r.date)
    end = ordered[-1].date
    start = end - timedelta(days=days - 1)
    return [r for r in ordered if r.date >= start]


def _confidence(readings_in_window: int, window_days: int, margin_frac: float) -> float:
    completeness = min(1.0, readings_in_window / window_days)
    margin = min(1.0, abs(margin_frac))
    return round(0.5 * completeness + 0.5 * (0.5 + 0.5 * margin), 2)


def check_trigger(readings: list[Reading], crop: str, stage: Stage, policy: Policy) -> TriggerResult:
    _validate(policy)
    if not readings:
        raise ValueError("check_trigger() needs at least one weather reading")
    spec = get_crop(crop)
    win = _window(readings, policy.window_days)
    rule = RULE_NAMES[policy.type]
    evidence: dict[str, Any] = {
        "crop": spec.key,
        "stage": stage.name,
        "stage_is_critical": stage.is_critical,
        "window_days": policy.window_days,
        "window_start": win[0].date.isoformat(),
        "window_end": win[-1].date.isoformat(),
        "readings_in_window": len(win),
    }

    if policy.type == "drought":
        threshold = float(policy.rainfall_threshold_mm)  # type: ignore[arg-type]
        total = round(sum(r.rainfall_mm for r in win), 1)
        dry_days = sum(1 for r in win if r.rainfall_mm < DRY_DAY_MM)
        condition = total < threshold
        evidence.update(
            {
                "rainfall_total_mm": total,
                "threshold_mm": threshold,
                "deficit_mm": round(max(0.0, threshold - total), 1),
                "dry_days": dry_days,
                "stage_water_need_mm_week": stage.water_need_mm_week,
            }
        )
        margin = (threshold - total) / threshold if threshold else 1.0

    elif policy.type == "excess_rain":
        threshold = float(policy.rainfall_threshold_mm)  # type: ignore[arg-type]
        ordered = sorted(readings, key=lambda r: r.date)
        best_total, best_start, best_end = -1.0, ordered[0].date, ordered[-1].date
        for i in range(len(ordered)):
            start = ordered[i].date
            chunk = [r for r in ordered[i:] if r.date < start + timedelta(days=policy.window_days)]
            t = sum(r.rainfall_mm for r in chunk)
            if t > best_total:
                best_total, best_start, best_end = t, start, chunk[-1].date
        best_total = round(best_total, 1)
        condition = best_total > threshold
        evidence.update(
            {
                "max_window_total_mm": best_total,
                "threshold_mm": threshold,
                "excess_mm": round(max(0.0, best_total - threshold), 1),
                "window_start": best_start.isoformat(),
                "window_end": best_end.isoformat(),
                "heavy_rain_72h_threshold_mm": spec.heavy_rain_72h_mm,
            }
        )
        margin = (best_total - threshold) / threshold if threshold else 1.0

    else:  # heat
        t_thr = float(policy.temp_threshold_c)  # type: ignore[arg-type]
        n_thr = int(policy.hot_days_threshold)  # type: ignore[arg-type]
        hot = [r for r in win if r.temp_max_c > t_thr]
        condition = len(hot) >= n_thr
        evidence.update(
            {
                "hot_days": len(hot),
                "hot_days_threshold": n_thr,
                "temp_threshold_c": t_thr,
                "peak_temp_c": max(r.temp_max_c for r in win),
                "crop_max_temp_c": stage.max_temp_c,
            }
        )
        margin = (len(hot) - n_thr) / max(n_thr, 1)

    triggered = bool(condition)
    if policy.critical_stages_only and not stage.is_critical:
        evidence["stage_gate_blocked"] = True
        evidence["condition_met"] = triggered
        triggered = False
    else:
        evidence["stage_gate_blocked"] = False

    return TriggerResult(
        triggered=triggered,
        rule=rule,
        evidence=evidence,
        confidence=_confidence(len(win), policy.window_days, margin),
        policy=policy,
    )
