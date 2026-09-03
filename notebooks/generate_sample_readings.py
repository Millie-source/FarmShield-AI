"""Generate backend/app/data/sample_readings.json - 30 days of realistic Juja readings
for three scenarios: normal, dry_spell, heavy_rain.

Climatology (Juja / JKUAT, 1,500 m, early September = end of the cool dry season):
  Tmax 25-29 C, Tmin 12-16 C, RH 55-70 %, occasional light showers, ETo ~4.5 mm/day.
Deterministic (seeded) so tests are reproducible.  Re-run:  python notebooks/generate_sample_readings.py
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

BASE_DATE = date(2026, 9, 3)
DAYS = 30
OUT = Path(__file__).resolve().parents[1] / "backend" / "app" / "data" / "sample_readings.json"


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def soil_walk(prev: float, rain: float, tmax: float, floor: float = 12.0, cap: float = 48.0) -> float:
    """Simple bucket model: rain recharges, hot days dry the top soil."""
    et_loss = 0.5 + max(0.0, tmax - 27) * 0.15  # evaporation, stronger on hot days
    drainage = max(0.0, prev - 20.0) * 0.03  # slow drainage above ~20 % VWC
    recharge = rain * 0.7
    return round(clamp(prev + recharge - et_loss - drainage, floor, cap), 1)


def build(scenario: str, rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    soil = 30.0
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

        soil = soil_walk(soil, rain, tmax)
        rows.append(
            {
                "day_offset": offset,
                "date": d.isoformat(),
                "rainfall_mm": rain,
                "temp_max_c": tmax,
                "temp_min_c": tmin,
                "humidity_pct": rh,
                "soil_moisture_pct": soil,
                "solar_radiation_wm2": solar,
                "wind_speed_ms": round(rng.uniform(1.5, 4.5), 1),
            }
        )
    return rows


def main() -> None:
    rng = random.Random(2026)
    data = {
        "station": "JKUAT Conduit Weather Station (synthetic replay)",
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
        print(f"{s:11s} rain7={r7:6.1f}mm rain30={r30:6.1f}mm  soil_last={rows[-1]['soil_moisture_pct']}%  tmax_last={rows[-1]['temp_max_c']}C")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
