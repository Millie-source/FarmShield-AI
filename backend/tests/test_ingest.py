"""GeoCSV parsing + resampling of Conduit@Empathy station records."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.ingest import geocsv, resample
from app.ingest.geocsv import EAT

HEADER = (
    "Time,Health,Battery Voltage,Rain Gauge 1,Rain Gauge 2,SHT Temperature (C),SHT Humidity (%),Wind Speed,"
    "Heat Index,Wet Bulb Temperature,Wet Bulb Globe Temperature,SI1145 Visible,SI1145 Infrared"
)


def make_geocsv(days: int = 3, step_min: int = 10, start: date = date(2026, 8, 20)) -> str:
    """Synthetic station export: a hot dry day, a rainy day, a normal day; plus dirty rows."""
    lines = ["# dataset: Conduit@Empathy1", "# sensor_id: 61", "# field_unit: Time=ISO8601", HEADER]
    t0 = datetime(start.year, start.month, start.day, 0, 0)
    n = days * 24 * 60 // step_min
    for i in range(n):
        t = t0 + timedelta(minutes=i * step_min)
        day = (t - t0).days
        hour = t.hour + t.minute / 60
        diurnal = -5 * abs(hour - 14) / 14  # peak at 14:00
        if day == 0:  # hot, dry, sunny
            temp, rh, rain, vis, ir = 33 + diurnal, 35, 0.0, 800 * max(0, 1 - abs(hour - 12) / 6), 300
        elif day == 1:  # rainy
            temp, rh, rain, vis, ir = 24 + diurnal, 90, 0.4 if 10 <= hour <= 18 else 0.0, 200, 120
        else:
            temp, rh, rain, vis, ir = 27 + diurnal, 60, 0.0, 500, 250
        hi = temp + (2 if rh > 80 else -1)
        wbgt = temp - 5
        gauge2 = rain if i % 7 else ""  # gauge 2 occasionally blank
        lines.append(f"{t.isoformat()},0,4.1,{rain},{gauge2},{temp:.1f},{rh},{2.5 + (i % 5)},{hi:.1f},{temp - 7:.1f},{wbgt:.1f},{vis:.0f},{ir}")
    # dirty rows: unhealthy, duplicate timestamp, blank temperature, stray blank line
    lines.append(f"{(t0 + timedelta(minutes=5)).isoformat()},3,4.1,99,99,60,10,1,60,50,55,1,1")  # Health=3 -> dropped
    lines.append(f"{t0.isoformat()},0,4.1,50,50,50,50,1,50,40,45,1,1")  # duplicate of first timestamp -> dropped
    lines.append(f"{(t0 + timedelta(days=days, minutes=1)).isoformat()},0,4.1,,,,,,,,,,")  # blanks -> NaN row
    lines.append("")
    return "\n".join(lines)


@pytest.fixture(scope="module")
def records():
    return geocsv.parse_geocsv_text(make_geocsv())


def test_metadata_skipped_and_dirty_rows_handled(records):
    n_expected = 3 * 24 * 6 + 1  # clean rows + the blank-values row (valid time)
    assert len(records) == n_expected
    first = records[0]
    assert first["time"] == datetime(2026, 8, 20, 0, 0, tzinfo=EAT)
    assert first["temp"] != 50  # duplicate timestamp kept the FIRST row
    assert all(r.get("health") in (0, None) for r in records)
    assert records[-1]["temp"] is None and records[-1]["rain_mm"] is None  # blanks -> None


def test_column_aliases_tolerate_units_and_case():
    cmap = geocsv.build_column_map(["TIME", "sht temperature (C)", "Wet Bulb Globe Temperature", "Rain Gauge 1", "unknown col"])
    assert cmap["time"] == "TIME" and cmap["temp"] == "sht temperature (C)" and cmap["wbgt"] and cmap["rain1"]
    assert "rh" not in cmap  # missing columns are simply absent


def test_rain_uses_max_of_gauges_and_light_sums_vis_ir(records):
    r = records[1]
    assert r["rain_mm"] == 0.0
    assert r["light"] == pytest.approx(300 + 800 * max(0, 1 - abs(10 / 60 - 12) / 6), abs=1)


def test_missing_time_column_raises():
    with pytest.raises(ValueError):
        geocsv.normalise_rows([{"temp": 1}])


def test_cumulative_rain_conversion():
    recs = [{"time": datetime(2026, 1, 1, 0, i, tzinfo=EAT), "rain_mm": v} for i, v in enumerate([10.0, 10.2, 10.2, 0.1, None, 0.3])]
    out = geocsv.rain_from_cumulative(recs)  # type: ignore[arg-type]
    assert [r["rain_mm"] for r in out] == [10.0, pytest.approx(0.2), 0.0, 0.1, None, pytest.approx(0.2)]


def test_hourly_and_daily_aggregates(records):
    hours = resample.hourly(records)
    assert len(hours) == 3 * 24 + 1
    assert hours[14]["temp_max_c"] == pytest.approx(33.0, abs=0.2)  # 14:00 on the hot day

    days = resample.daily(records)
    assert [d["date"] for d in days] == [date(2026, 8, 20), date(2026, 8, 21), date(2026, 8, 22)]  # 1-record day dropped
    hot, wet, normal = days
    assert hot["temp_max_c"] == pytest.approx(33.0, abs=0.1) and hot["temp_min_c"] == pytest.approx(28.0, abs=0.1)
    assert hot["rainfall_mm"] == 0.0 and hot["humidity_pct"] == 35
    assert wet["rainfall_mm"] == pytest.approx(0.4 * 49, abs=0.5)  # 10:00-18:00 inclusive at 10-min steps
    assert wet["heat_index_max_c"] > wet["temp_max_c"]
    assert hot["wbgt_max_c"] == pytest.approx(28.0, abs=0.1)
    assert hot["wind_gust_ms"] == 6.5 and 4 <= hot["wind_speed_ms"] <= 5
    assert hot["light_index"] == 1.0 and wet["light_index"] < 0.5  # normalised to file max
    assert hot["n_records"] == 144 and hot["coverage_pct"] == 10.0
    assert all(d["soil_moisture_pct"] is None for d in days)  # station has no probe


def test_readings_roundtrip_through_daily_csv(records, tmp_path):
    days = resample.daily(records)
    path = resample.write_daily_csv(days, tmp_path / "daily.csv")
    back = resample.read_daily_csv(path)
    readings = resample.to_readings(back)
    assert len(readings) == 3 and not readings[0].synthetic
    assert readings[0].wbgt_max_c == pytest.approx(28.0, abs=0.1) and readings[0].soil_moisture_pct is None
    assert readings[1].rainfall_mm > 15


def test_api_json_rows_normalise_to_the_same_shape():
    rows = [
        {"Time": "2026-09-01T12:00:00Z", "Health": "0", "Rain Gauge 1": "0.2", "SHT Temperature": "29.5", "SHT Humidity": "50", "Wet Bulb Globe Temperature": "26"},
        {"Time": "2026-09-01T12:01:00Z", "Health": "0", "Rain Gauge 1": "", "SHT Temperature": "29.7", "SHT Humidity": "49", "Wet Bulb Globe Temperature": "26.2"},
    ]
    recs = geocsv.normalise_rows(rows)
    assert recs[0]["time"].hour == 15  # UTC -> EAT
    assert recs[1]["rain_mm"] is None and recs[1]["wbgt"] == 26.2
    assert resample.daily(recs, min_records=1)[0]["wbgt_max_c"] == 26.2
