from datetime import timedelta

import pytest

from app.engine.crops import CROPS, OVERALL_WEIGHTS
from app.engine.scoring import assess
from app.engine.stages import derive_stage
from tests.conftest import TODAY, make_readings


def stage(crop: str, days_ago: int):
    return derive_stage(crop, TODAY - timedelta(days=days_ago), TODAY)


MAIZE_FLOWERING = ("maize", 62)
BEANS_VEGETATIVE = ("beans", 25)
KALE_PLANTED = ("kale", 5)


# ---------------------------------------------------------------- drought ----
def test_drought_high_for_maize_flowering_in_dry_spell(dry_spell):
    a = assess(dry_spell, "maize", stage(*MAIZE_FLOWERING))
    assert a.drought.level == "HIGH"
    assert a.drought.score >= 65
    joined = " ".join(a.drought.reasons).lower()
    assert "mm" in joined and "7 days" in joined  # rainfall-deficit evidence
    assert "flowering" in joined


def test_drought_low_in_heavy_rain(heavy_rain):
    a = assess(heavy_rain, "maize", stage(*MAIZE_FLOWERING))
    assert a.drought.level == "LOW"


def test_drought_ranks_scenarios(normal, dry_spell, heavy_rain):
    st = stage(*MAIZE_FLOWERING)
    d = {n: assess(r, "maize", st).drought.score for n, r in [("dry", dry_spell), ("normal", normal), ("wet", heavy_rain)]}
    assert d["dry"] > d["normal"] > d["wet"]


def test_drought_modelled_soil_drains_to_wilting_and_says_modelled():
    readings = make_readings(rain=0.0, tmax=31.0)  # no probe: bucket is modelled
    a = assess(readings, "maize", stage(*MAIZE_FLOWERING))
    assert a.soil_moisture_source == "modelled"
    assert a.soil_moisture_pct < CROPS["maize"].stress_soil_pct  # 30 dry days drain the bucket past the stress threshold
    assert any("modelled soil moisture" in r.lower() for r in a.drought.reasons)
    assert a.drought.level == "HIGH"


def test_drought_uses_measured_soil_when_probe_present():
    readings = make_readings(rain=0.0, soil=14.0)
    a = assess(readings, "maize", stage(*MAIZE_FLOWERING))
    assert a.soil_moisture_source == "measured" and a.soil_moisture_pct == 14.0
    assert any("measured soil moisture" in r.lower() for r in a.drought.reasons)


def test_drought_weighted_higher_at_flowering_than_maturity(dry_spell):
    flowering = assess(dry_spell, "maize", stage("maize", 62)).drought.score
    maturity = assess(dry_spell, "maize", stage("maize", 115)).drought.score
    assert flowering > maturity


# ------------------------------------------------------------------ flood ----
def test_flood_high_in_heavy_rain(heavy_rain):
    a = assess(heavy_rain, "kale", stage(*KALE_PLANTED))
    assert a.flood.level == "HIGH"
    joined = " ".join(a.flood.reasons).lower()
    assert "72" in joined or "24" in joined
    assert "mm" in joined


def test_flood_low_in_dry_spell(dry_spell):
    a = assess(dry_spell, "maize", stage(*MAIZE_FLOWERING))
    assert a.flood.level == "LOW"
    assert a.flood.score < 15


def test_flood_modelled_saturation_adds_reason():
    readings = make_readings(rain=45.0, tmax=23.0, humidity=90.0)  # 45 mm every day saturates the bucket
    a = assess(readings, "beans", stage(*BEANS_VEGETATIVE))
    assert a.soil_moisture_pct >= 40
    assert any("modelled soil moisture" in r.lower() and ("saturat" in r.lower() or "waterlog" in r.lower()) for r in a.flood.reasons)


# ------------------------------------------------------------------- heat ----
def test_heat_elevated_for_maize_flowering_in_dry_spell(dry_spell):
    a = assess(dry_spell, "maize", stage(*MAIZE_FLOWERING))
    assert a.heat.level in ("MEDIUM", "HIGH")
    assert any("°c" in r.lower() or "c " in r.lower() for r in a.heat.reasons)


def test_heat_lower_in_normal_than_dry_spell(normal, dry_spell):
    st = stage(*MAIZE_FLOWERING)
    assert assess(normal, "maize", st).heat.score < assess(dry_spell, "maize", st).heat.score


def test_heat_uses_tighter_threshold_at_flowering():
    # 33 C: above maize flowering limit (32) but below general limit (35)
    readings = make_readings(tmax=33.0, humidity=45.0)
    flowering = assess(readings, "maize", stage("maize", 62)).heat.score
    vegetative = assess(readings, "maize", stage("maize", 35)).heat.score
    assert flowering > vegetative


def test_heat_reads_station_wbgt_when_tmax_is_moderate():
    # Tmax 30 is under the maize flowering limit (32) but a WBGT of 31 is far above the WBGT limit
    cool_air = assess(make_readings(tmax=30.0, humidity=80.0), "maize", stage("maize", 62))
    humid = assess(make_readings(tmax=30.0, humidity=80.0, wbgt=31.0), "maize", stage("maize", 62))
    assert cool_air.heat_metric == "tmax" and cool_air.heat.score < humid.heat.score
    assert humid.heat_metric == "wbgt"
    assert any("wbgt" in r.lower() for r in humid.heat.reasons)


def test_heat_reads_heat_index_when_present():
    a = assess(make_readings(tmax=30.0, humidity=80.0, heat_index=40.0), "beans", stage("beans", 40))
    assert a.heat_metric == "heat_index" and a.heat.level in ("MEDIUM", "HIGH")


def test_low_humidity_amplifies_heat():
    dry_air = assess(make_readings(tmax=33.0, humidity=30.0), "maize", stage("maize", 62)).heat.score
    humid = assess(make_readings(tmax=33.0, humidity=70.0), "maize", stage("maize", 62)).heat.score
    assert dry_air > humid


# ------------------------------------------------------------ crop health ----
def test_crop_health_uses_ndvi_when_available(normal):
    good = assess(normal, "maize", stage(*MAIZE_FLOWERING), ndvi=0.78)
    poor = assess(normal, "maize", stage(*MAIZE_FLOWERING), ndvi=0.28)
    assert good.crop_health.label == "GOOD"
    assert poor.crop_health.label == "POOR"
    assert any("ndvi" in r.lower() for r in good.crop_health.reasons)


def test_crop_health_derived_from_stress_without_ndvi(normal, dry_spell):
    stressed = assess(dry_spell, "maize", stage(*MAIZE_FLOWERING)).crop_health
    fine = assess(normal, "kale", stage(*KALE_PLANTED)).crop_health
    assert stressed.label in ("FAIR", "POOR")
    assert fine.label == "GOOD"
    assert stressed.score > fine.score


# ---------------------------------------------------------------- overall ----
def test_demo_farm_maize_flowering_dry_spell_is_high(dry_spell):
    a = assess(dry_spell, "maize", stage(*MAIZE_FLOWERING))
    assert a.overall.level == "HIGH"
    assert a.overall.label == "HIGH CLIMATE RISK"
    assert a.overall.score >= 65
    assert any("rain" in r.lower() and "mm" in r for r in a.all_reasons)


def test_demo_farm_kale_just_planted_normal_is_low(normal):
    a = assess(normal, "kale", stage(*KALE_PLANTED))
    assert a.overall.level == "LOW"
    assert a.overall.label == "LOW CLIMATE RISK"


def test_demo_farm_beans_vegetative_normal_is_medium(normal):
    a = assess(normal, "beans", stage(*BEANS_VEGETATIVE))
    assert a.overall.level == "MEDIUM"
    assert a.overall.label == "MODERATE CLIMATE RISK"


def test_overall_uses_stage_dependent_weights(dry_spell, heavy_rain):
    crit = assess(dry_spell, "maize", stage("maize", 62))
    est = assess(heavy_rain, "maize", stage("maize", 5))
    assert crit.overall.weights == OVERALL_WEIGHTS["critical"]
    assert est.overall.weights == OVERALL_WEIGHTS["establishment"]
    for w in OVERALL_WEIGHTS.values():
        assert sum(w.values()) == pytest.approx(1.0)


def test_overall_not_diluted_below_weighted_mean(dry_spell):
    a = assess(dry_spell, "maize", stage(*MAIZE_FLOWERING))
    subs = {k: v.score for k, v in a.sub_scores.items()}
    weighted = sum(subs[k] * w for k, w in a.overall.weights.items())
    assert a.overall.score >= round(weighted) - 1
    assert a.overall.score <= max(subs.values())


@pytest.mark.parametrize("scenario_name", ["normal", "dry_spell", "heavy_rain"])
@pytest.mark.parametrize("crop", list(CROPS))
def test_every_sub_score_has_reasons_and_valid_range(scenario_name, crop, request):
    readings = request.getfixturevalue(scenario_name)
    spec = CROPS[crop]
    for days_ago in (3, spec.season_length_days // 2, spec.season_length_days - 2):
        a = assess(readings, crop, stage(crop, days_ago))
        for name, s in a.sub_scores.items():
            assert 0 <= s.score <= 100, name
            assert s.level in ("LOW", "MEDIUM", "HIGH"), name
            assert len(s.reasons) >= 1, f"{name} has no reasons"
        assert 0 <= a.overall.score <= 100
        assert a.to_dict()["overall"]["label"].endswith("CLIMATE RISK")


def test_assess_requires_readings():
    with pytest.raises(ValueError):
        assess([], "maize", stage(*MAIZE_FLOWERING))


def test_assess_handles_short_history(dry_spell):
    a = assess(dry_spell[-3:], "maize", stage(*MAIZE_FLOWERING))
    assert a.readings_used == 3
    assert a.overall.score > 0
