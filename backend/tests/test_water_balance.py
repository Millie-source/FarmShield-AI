"""Water balance: Hargreaves ET0 and the soil bucket that replaces the missing soil probe."""
from datetime import date, timedelta

import pytest

from app.engine.crops import get_crop
from app.engine.water_balance import DEFAULT_SOIL, SOIL_TYPES, et0_hargreaves, extraterrestrial_radiation_mj, kc_on_day, simulate
from tests.conftest import TODAY, make_readings

MAIZE = get_crop("maize")
PLANTED = TODAY - timedelta(days=62)  # flowering


def test_extraterrestrial_radiation_near_equator_is_high_all_year():
    ra = [extraterrestrial_radiation_mj(-1.0997, doy) for doy in (1, 80, 172, 266, 355)]
    assert all(31 < r < 39 for r in ra), ra  # FAO-56 Annex 2 table: ~33-38 MJ/m2/day at 0-2 S


def test_et0_matches_juja_climatology():
    # Sep in Juja: Tmax ~27, Tmin ~14 -> CLIMWAT "Thika" ET0 ~4.5 mm/day
    et0 = et0_hargreaves(14.0, 27.0, None, -1.0997, date(2026, 9, 3).timetuple().tm_yday)
    assert 3.8 <= et0 <= 5.2, et0
    hot = et0_hargreaves(16.0, 34.0, None, -1.0997, 246)
    assert hot > et0
    assert et0_hargreaves(20.0, 20.0, None, -1.0997, 246) == 0.0  # no diurnal range -> no ET (Hargreaves limit)


def test_light_index_only_nudges_et0():
    base = et0_hargreaves(14.0, 27.0, None, -1.0997, 246)
    assert et0_hargreaves(14.0, 27.0, None, -1.0997, 246, light_index=1.0) == pytest.approx(base * 1.10, rel=0.01)
    assert et0_hargreaves(14.0, 27.0, None, -1.0997, 246, light_index=0.0) == pytest.approx(base * 0.90, rel=0.01)
    assert et0_hargreaves(14.0, 27.0, None, -1.0997, 246, light_index=0.5) == pytest.approx(base, rel=0.01)


def test_kc_follows_the_crop_calendar():
    assert kc_on_day(MAIZE, -5) == 0.30  # bare soil before planting
    assert kc_on_day(MAIZE, 5) == MAIZE.stages[0].kc
    assert kc_on_day(MAIZE, 62) == MAIZE.stages[2].kc  # flowering, Kc 1.2
    assert kc_on_day(MAIZE, 500) == MAIZE.stages[-1].kc


def test_dry_week_drains_the_bucket():
    week = make_readings(days=7, rain=0.0, tmax=31.0, tmin=15.0)
    bal = simulate(week, MAIZE, PLANTED)
    series = [b.soil_moisture_pct for b in bal]
    assert series == sorted(series, reverse=True)  # monotonically drying
    assert series[0] - series[-1] >= 4.0  # ~5.5 mm/day ETc over 600 mm -> ~1 %/day
    assert all(b.etc_mm > 3 for b in bal[:3])
    assert all(b.rain_mm == 0 and b.runoff_mm == 0 for b in bal)


def test_forty_mm_day_fills_the_bucket():
    dry = make_readings(days=20, rain=0.0, tmax=31.0)
    wet_day = make_readings(days=1, rain=40.0, tmax=24.0, humidity=90.0, end=TODAY + timedelta(days=1))
    bal = simulate(dry + wet_day, MAIZE, PLANTED)
    before, after = bal[-2].soil_moisture_pct, bal[-1].soil_moisture_pct
    assert before < DEFAULT_SOIL.field_capacity_pct - 5
    assert after - before >= 5.0  # 40 mm over a 600 mm root zone ~ +6.7 % VWC
    assert after <= DEFAULT_SOIL.saturation_pct


def test_saturated_soil_produces_runoff_and_drains_back_to_field_capacity():
    storm = make_readings(days=5, rain=80.0, tmax=22.0, humidity=95.0)
    calm = make_readings(days=6, rain=0.0, tmax=26.0, end=TODAY + timedelta(days=6))
    bal = simulate(storm + calm, MAIZE, PLANTED)
    assert any(b.runoff_mm > 0 for b in bal[:5])
    assert bal[4].soil_moisture_pct >= DEFAULT_SOIL.field_capacity_pct
    assert bal[-1].soil_moisture_pct < bal[4].soil_moisture_pct  # excess water drains after the storm


def test_never_below_wilting_point_or_above_saturation():
    bal = simulate(make_readings(days=60, rain=0.0, tmax=36.0, tmin=20.0), MAIZE, PLANTED)
    assert bal[-1].soil_moisture_pct <= DEFAULT_SOIL.wilting_point_pct + 0.5  # Ks -> 0 as the bucket nears wilting
    bal = simulate(make_readings(days=10, rain=200.0, tmax=22.0), MAIZE, PLANTED)
    assert all(b.soil_moisture_pct <= DEFAULT_SOIL.saturation_pct for b in bal)


def test_measured_probe_value_resets_the_bucket():
    readings = make_readings(days=5, rain=0.0) + make_readings(days=1, rain=0.0, soil=40.0, end=TODAY + timedelta(days=1))
    bal = simulate(readings, MAIZE, PLANTED)
    assert bal[-1].measured is True
    assert bal[-1].soil_moisture_pct == 40.0  # the probe value is reported as-is
    after = simulate(readings + make_readings(days=1, rain=0.0, end=TODAY + timedelta(days=2)), MAIZE, PLANTED)[-1]
    assert after.measured is False and 37.0 <= after.soil_moisture_pct < 40.0  # bucket restarts from the probe value


def test_other_soil_types_available():
    sandy = simulate(make_readings(days=7, rain=0.0, tmax=31.0), MAIZE, PLANTED, soil=SOIL_TYPES["sandy_loam"])
    assert sandy[-1].soil_moisture_pct < DEFAULT_SOIL.wilting_point_pct  # sandy loam holds less water
