"""Resample 1-minute station records to hourly and daily aggregates, and to engine Readings.

Daily aggregate (what the engine consumes):
    rain sum, T min/max/mean, RH mean, wind mean / gust max, Heat Index max, WBGT max,
    light index (max of SI1145 visible+IR, normalised 0-1 to the file maximum), soil (mean, if present).
Days with fewer than ``min_records`` records are dropped (a handful of packets is not a day).
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from app.engine.types import Reading

from .geocsv import RawRecord

DAILY_COLUMNS = [
    "date", "rainfall_mm", "temp_max_c", "temp_min_c", "temp_mean_c", "humidity_pct", "wind_speed_ms", "wind_gust_ms",
    "heat_index_max_c", "wbgt_max_c", "light_raw_max", "light_index", "soil_moisture_pct", "n_records", "coverage_pct",
]
EXPECTED_RECORDS_PER_DAY = 1440  # 1-minute cadence


def _vals(recs: Iterable[RawRecord], key: str) -> list[float]:
    return [r[key] for r in recs if r.get(key) is not None]  # type: ignore[misc]


def _agg(recs: list[RawRecord]) -> dict[str, Any]:
    t, rh, wind, hi, wbgt, light, soil = (_vals(recs, k) for k in ("temp", "rh", "wind", "heat_index", "wbgt", "light", "soil"))
    rain = _vals(recs, "rain_mm")
    return {
        "rainfall_mm": round(sum(rain), 1) if rain else None,
        "temp_max_c": round(max(t), 1) if t else None,
        "temp_min_c": round(min(t), 1) if t else None,
        "temp_mean_c": round(mean(t), 1) if t else None,
        "humidity_pct": round(mean(rh), 0) if rh else None,
        "wind_speed_ms": round(mean(wind), 1) if wind else None,
        "wind_gust_ms": round(max(wind), 1) if wind else None,
        "heat_index_max_c": round(max(hi), 1) if hi else None,
        "wbgt_max_c": round(max(wbgt), 1) if wbgt else None,
        "light_raw_max": round(max(light), 0) if light else None,
        "soil_moisture_pct": round(mean(soil), 1) if soil else None,
        "n_records": len(recs),
    }


def hourly(records: list[RawRecord]) -> list[dict[str, Any]]:
    buckets: dict[datetime, list[RawRecord]] = defaultdict(list)
    for r in records:
        buckets[r["time"].replace(minute=0, second=0, microsecond=0)].append(r)
    return [{"hour": h, **_agg(buckets[h])} for h in sorted(buckets)]


def daily(records: list[RawRecord], min_records: int = 12, light_max: float | None = None) -> list[dict[str, Any]]:
    """Daily rows (local EAT dates). ``light_max`` fixes the normalisation reference (e.g. across API chunks)."""
    buckets: dict[date, list[RawRecord]] = defaultdict(list)
    for r in records:
        buckets[r["time"].date()].append(r)
    rows = []
    for d in sorted(buckets):
        recs = buckets[d]
        if len(recs) < min_records:
            continue
        a = _agg(recs)
        if a["temp_max_c"] is None:
            continue  # a day without temperature cannot be scored
        a["coverage_pct"] = round(100 * len(recs) / EXPECTED_RECORDS_PER_DAY, 1)
        rows.append({"date": d, **a})
    ref = light_max or max((r["light_raw_max"] for r in rows if r["light_raw_max"]), default=None)
    for r in rows:
        r["light_index"] = round(r["light_raw_max"] / ref, 2) if (ref and r["light_raw_max"] is not None) else None
    return rows


def to_readings(daily_rows: Iterable[dict[str, Any]], synthetic: bool = False) -> list[Reading]:
    out: list[Reading] = []
    for r in daily_rows:
        if r.get("temp_max_c") is None or r.get("temp_min_c") is None:
            continue
        out.append(
            Reading(
                date=r["date"] if isinstance(r["date"], date) else date.fromisoformat(str(r["date"])),
                rainfall_mm=float(r.get("rainfall_mm") or 0.0),
                temp_max_c=float(r["temp_max_c"]),
                temp_min_c=float(r["temp_min_c"]),
                humidity_pct=float(r["humidity_pct"]) if r.get("humidity_pct") is not None else 60.0,
                temp_mean_c=_f(r.get("temp_mean_c")),
                wind_speed_ms=_f(r.get("wind_speed_ms")),
                wind_gust_ms=_f(r.get("wind_gust_ms")),
                heat_index_max_c=_f(r.get("heat_index_max_c")),
                wbgt_max_c=_f(r.get("wbgt_max_c")),
                light_index=_f(r.get("light_index")),
                soil_moisture_pct=_f(r.get("soil_moisture_pct")),
                synthetic=synthetic,
            )
        )
    return out


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def write_daily_csv(rows: Iterable[dict[str, Any]], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=DAILY_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "date": r["date"].isoformat() if isinstance(r["date"], date) else r["date"]})
    return path


def read_daily_csv(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        rows = []
        for r in csv.DictReader(fh):
            row: dict[str, Any] = {k: _f(v) for k, v in r.items() if k != "date"}
            row["date"] = date.fromisoformat(r["date"])
            rows.append(row)
    return sorted(rows, key=lambda r: r["date"])
