from datetime import timedelta

import pytest

from app.engine.insurance import check_trigger
from app.engine.stages import derive_stage
from app.engine.types import Policy
from tests.conftest import TODAY, make_readings


def stage(crop: str, days_ago: int):
    return derive_stage(crop, TODAY - timedelta(days=days_ago), TODAY)


DROUGHT_21_30 = Policy(type="drought", window_days=21, rainfall_threshold_mm=30)
EXCESS_3_100 = Policy(type="excess_rain", window_days=3, rainfall_threshold_mm=100)
HEAT_14 = Policy(type="heat", window_days=14, temp_threshold_c=32, hot_days_threshold=5)


# --------------------------------------------------------- drought trigger ----
def test_drought_trigger_fires_for_maize_flowering_in_dry_spell(dry_spell):
    r = check_trigger(dry_spell, "maize", stage("maize", 62), DROUGHT_21_30)
    assert r.triggered is True
    assert r.rule == "drought_rainfall_deficit"
    ev = r.evidence
    assert ev["window_days"] == 21
    assert ev["rainfall_total_mm"] < 30
    assert ev["threshold_mm"] == 30
    assert ev["deficit_mm"] == pytest.approx(30 - ev["rainfall_total_mm"], abs=0.11)
    assert ev["dry_days"] >= 14
    assert ev["stage"] == "flowering"
    assert r.confidence >= 0.7


def test_drought_trigger_does_not_fire_in_normal(normal):
    r = check_trigger(normal, "maize", stage("maize", 62), DROUGHT_21_30)
    assert r.triggered is False
    assert r.rule == "drought_rainfall_deficit"
    assert r.evidence["rainfall_total_mm"] >= 30 or r.evidence.get("stage_gate_blocked")


def test_drought_trigger_respects_critical_stage_gate(dry_spell):
    gated = Policy(type="drought", window_days=21, rainfall_threshold_mm=30, critical_stages_only=True)
    # kale at establishment (sensitivity 0.5) is not a critical stage -> no payout
    r = check_trigger(dry_spell, "kale", stage("kale", 5), gated)
    assert r.triggered is False
    assert r.evidence["stage_gate_blocked"] is True
    # maize at flowering is critical -> payout
    r2 = check_trigger(dry_spell, "maize", stage("maize", 62), gated)
    assert r2.triggered is True


def test_drought_confidence_drops_with_incomplete_data(dry_spell):
    full = check_trigger(dry_spell, "maize", stage("maize", 62), DROUGHT_21_30)
    partial = check_trigger(dry_spell[-10:], "maize", stage("maize", 62), DROUGHT_21_30)
    assert partial.confidence < full.confidence
    assert partial.evidence["readings_in_window"] == 10


# ----------------------------------------------------- excess-rain trigger ----
def test_excess_rain_trigger_fires_in_heavy_rain(heavy_rain):
    r = check_trigger(heavy_rain, "kale", stage("kale", 5), EXCESS_3_100)
    assert r.triggered is True
    assert r.rule == "excess_rainfall"
    assert r.evidence["max_window_total_mm"] > 100
    assert "window_start" in r.evidence and "window_end" in r.evidence


def test_excess_rain_trigger_silent_in_normal_and_dry(normal, dry_spell):
    assert check_trigger(normal, "kale", stage("kale", 5), EXCESS_3_100).triggered is False
    assert check_trigger(dry_spell, "kale", stage("kale", 5), EXCESS_3_100).triggered is False


# ------------------------------------------------------------ heat trigger ----
def test_heat_trigger_fires_in_dry_spell(dry_spell):
    r = check_trigger(dry_spell, "maize", stage("maize", 62), HEAT_14)
    assert r.triggered is True
    assert r.rule == "heat_days"
    assert r.evidence["hot_days"] >= 5


def test_heat_trigger_silent_in_normal(normal):
    assert check_trigger(normal, "maize", stage("maize", 62), HEAT_14).triggered is False


# ---------------------------------------------------------------- general ----
def test_policy_requires_threshold():
    with pytest.raises(ValueError):
        check_trigger(make_readings(), "maize", stage("maize", 62), Policy(type="drought", window_days=21))


def test_trigger_result_serialises():
    d = check_trigger(make_readings(rain=0.0), "maize", stage("maize", 62), DROUGHT_21_30).to_dict()
    assert d["triggered"] is True
    assert d["policy"]["type"] == "drought"
    assert 0 <= d["confidence"] <= 1
