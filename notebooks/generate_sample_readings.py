"""Generate backend/app/data/sample_readings.json - 30 days of realistic Juja readings
for three SYNTHETIC scenarios: normal, dry_spell, heavy_rain (live "flip the weather" demo only;
real data comes from the Conduit CSV / API providers).

Climatology (Juja / JKUAT, 1,500 m, early September = end of the cool dry season):
  Tmax 25-29 C, Tmin 12-16 C, RH 55-70 %, occasional light showers, ETo ~4.5 mm/day.
Deterministic (seeded) so tests are reproducible.  Re-run:  python notebooks/generate_sample_readings.py
"""
from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

BASE_DATE = date(2026, 9, 3)
DAYS = 30
OUT = Path(__file__).resolve().parents[1] / "backend" / "app" / "data" / "sample_readings.json"


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def vapour_pressure_hpa(t_c: float, rh: float) -> float:
    return rh / 100 * 6.105 * math.exp(17.27 * t_c / (237.7 + t_c))


def heat_index_c(t_c: float, rh: float) -> float:
    """NOAA / Rothfusz heat index (valid above ~27 C); below that HI ~ T."""
    if t_c < 27:
        return round(t_c, 1)
    tf = t_c * 9 / 5 + 32
    hi = (-42.379 + 2.04901523 * tf + 10.14333127 * rh - 0.22475541 * tf * rh - 6.83783e-3 * tf**2
          - 5.481717e-2 * rh**2 + 1.22874e-3 * tf**2 * rh + 8.5282e-4 * tf * rh**2 - 1.99e-6 * tf**2 * rh**2)
    return round((hi - 32) * 5 / 9, 1)


def wet_bulb_c(t_c: float, rh: float) -> float:
    """Natural wet-bulb temperature, Stull (2011) empirical fit."""
    return (t_c * math.atan(0.151977 * math.sqrt(rh + 8.313659)) + math.atan(t_c + rh) - math.atan(rh - 1.676331)
            + 0.00391838 * rh**1.5 * math.atan(0.023101 * rh) - 4.686035)


def wbgt_c(t_c: float, rh: float, light: float) -> float:
    """Outdoor WBGT = 0.7 Tw + 0.2 Tg + 0.1 Ta with the black-globe excess scaled by the light index."""
    tg = t_c + 6.0 * light
    return round(0.7 * wet_bulb_c(t_c, rh) + 0.2 * tg + 0.1 * t_c, 1)


def build(scenario: str, rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    for i in range(DAYS):
        offset = i - (DAYS - 1)  # -29 .. 0
        d = BASE_DATE + timedelta(days=offset)
        if scenario == "normal":
            # Hand-authored late-dry-season pattern: light showers, a modest wet
            # spell 4-6 days ago (the kale farm was planted "after rain"), dry since.
            pattern = {-28: 3.0, -25: 5.5, -22: 2.0, -19: 4.5, -17: 7.0, -14: 3.5, -12: 6.0, -9: 2.5, -6: 4.0, -5: 6.0, -4: 3.0}
            rain = round(max(0.0, pattern.get(offset, 0.0) + (rng.uniform(-0.4, 0.4) if offset in pattern else 0.0)), 1)
            tmax = round(rng.uniform(26.0, 29.0), 1)
            tmin = round(rng.uniform(13.0, 16.0), 1)
            rh = round(rng.uniform(55, 70), 0)
            solar = round(rng.uniform(190, 240), 0)
        elif scenario == "dry_spell":
            if offset < -21:  # a few light showers before the spell sets in
                rain = round(max(0.0, rng.choice([0, 0, 3, 5]) + rng.uniform(-0.5, 0.5)), 1)
            else:
                rain = 0.4 if offset == -12 else 0.0  # one trace event, still a "dry day"
            ramp = clamp((offset + 21) / 21, 0, 1)  # heat builds through the spell
            tmax = round(29.0 + 4.5 * ramp + rng.uniform(-0.6, 0.6), 1)
            tmin = round(rng.uniform(14.0, 17.0), 1)
            rh = round(clamp(58 - 20 * ramp + rng.uniform(-3, 3), 30, 70), 0)
            solar = round(240 + 50 * ramp + rng.uniform(-10, 10), 0)
        elif scenario == "heavy_rain":
            if offset < -8:
                rain = round(max(0.0, rng.choice([0, 0, 2, 5, 8]) + rng.uniform(-0.5, 0.5)), 1)
                tmax = round(rng.uniform(25.0, 28.0), 1)
                rh = round(rng.uniform(60, 72), 0)
                solar = round(rng.uniform(180, 230), 0)
            else:
                burst = {-8: 12, -7: 28, -6: 45, -5: 62, -4: 38, -3: 55, -2: 31, -1: 48, 0: 36}
                rain = round(burst[offset] + rng.uniform(-2, 2), 1)
                tmax = round(rng.uniform(21.5, 24.5), 1)
                rh = round(rng.uniform(82, 94), 0)
                solar = round(rng.uniform(95, 150), 0)
            tmin = round(rng.uniform(13.0, 16.0), 1)
        else:
            raise ValueError(scenario)

        wind = round(rng.uniform(1.5, 4.5), 1)
        light = round(clamp(solar / 300.0, 0, 1), 2)
        rows.append(
            {
                "day_offset": offset,
                "date": d.isoformat(),
                "rainfall_mm": rain,
                "temp_max_c": tmax,
                "temp_min_c": tmin,
                "humidity_pct": rh,
                "wind_speed_ms": wind,
                "wind_gust_ms": round(wind * rng.uniform(1.8, 2.6), 1),
                # Station-style heat metrics (Conduit@Empathy exposes Heat Index + WBGT directly)
                "heat_index_max_c": heat_index_c(tmax, rh),
                "wbgt_max_c": wbgt_c(tmax, rh, light),
                # SI1145 visible+IR normalised to the file maximum (no W/m2 pyranometer on the station)
                "light_index": light,
            }
        )
    return rows


def main() -> None:
    rng = random.Random(2026)
    data = {
        "station": "JKUAT Conduit@Empathy1 (sensor 61) - SYNTHETIC demo scenarios, not measurements",
        "location": {"lat": -1.0955, "lon": 37.0144, "name": "Juja, Kiambu County"},
        "base_date": BASE_DATE.isoformat(),
        "days": DAYS,
        "scenarios": {s: build(s, rng) for s in ("normal", "dry_spell", "heavy_rain")},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    for s, rows in data["scenarios"].items():
        r7 = sum(r["rainfall_mm"] for r in rows[-7:])
        r30 = sum(r["rainfall_mm"] for r in rows)
        print(f"{s:11s} rain7={r7:6.1f}mm rain30={r30:6.1f}mm  wbgt_last={rows[-1]['wbgt_max_c']}C  tmax_last={rows[-1]['temp_max_c']}C")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
