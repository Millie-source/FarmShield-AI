"""Parse the Conduit@Empathy GeoCSV export (and API JSON rows) into normalised raw records.

GeoCSV = a CSV with ``#`` metadata lines before the header.  Expected columns (from the
station export; matching is case-insensitive, units in parentheses are ignored):

    Time, Health, Battery Voltage, ..., Rain Gauge 1, Rain Gauge 2, ..., SHT Temperature,
    SHT Humidity, ..., Wind Speed, ..., Heat Index, Wet Bulb Temperature,
    Wet Bulb Globe Temperature, SI1145 Visible, SI1145 Infrared, ...

Rules: skip ``#`` lines and blanks, ISO timestamps (naive = East Africa Time), blank cells ->
None, drop rows with ``Health != 0``, de-duplicate on Time (first wins), sort by time.
The mapper is tolerant of missing columns: anything absent is simply None downstream.

Output is a list of ``RawRecord`` dicts - the single shape ``resample.py`` consumes, whether
the rows came from the CSV export or from the API (see ``providers/weather/conduit_api.py``).
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, TypedDict

EAT = timezone(timedelta(hours=3), name="EAT")  # station local time (Africa/Nairobi, no DST)

COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "time": ("time", "timestamp", "datetime", "date", "recorded_at", "created_at"),
    "health": ("health", "status"),
    "battery_v": ("battery voltage", "battery", "vbat"),
    "rain1": ("rain gauge 1", "rain gauge1", "rain_gauge_1", "rain1", "rainfall", "rain", "precipitation"),
    "rain2": ("rain gauge 2", "rain gauge2", "rain_gauge_2", "rain2"),
    "temp": ("sht temperature", "temperature", "air temperature", "temp", "sht temp"),
    "rh": ("sht humidity", "humidity", "relative humidity", "rh"),
    "wind": ("wind speed", "wind_speed", "wind", "windspeed"),
    "wind_dir": ("wind direction", "wind_direction"),
    "heat_index": ("heat index", "heat_index", "hi"),
    "wet_bulb": ("wet bulb temperature", "wet bulb", "wet_bulb"),
    "wbgt": ("wet bulb globe temperature", "wbgt", "wet_bulb_globe_temperature"),
    "vis": ("si1145 visible", "visible", "si1145 vis", "light visible"),
    "ir": ("si1145 infrared", "infrared", "si1145 ir", "light infrared"),
    "uv": ("si1145 uv", "uv index", "uv"),
    "pressure": ("pressure", "barometric pressure", "bmp pressure"),
    "soil": ("soil moisture", "soil_moisture", "soil"),
}
RAIN_GAUGE_STRATEGY = "max"  # max | mean | gauge1 - max is robust to a stuck-at-zero gauge; confirm with probe data


class RawRecord(TypedDict, total=False):
    time: datetime
    health: int | None
    battery_v: float | None
    rain_mm: float | None
    temp: float | None
    rh: float | None
    wind: float | None
    heat_index: float | None
    wet_bulb: float | None
    wbgt: float | None
    light: float | None  # SI1145 visible + infrared raw counts
    uv: float | None
    soil: float | None


def normalise_key(name: str) -> str:
    """'SHT Temperature (C)' -> 'sht temperature'."""
    n = re.sub(r"\(.*?\)|\[.*?\]", "", str(name)).strip().lower()
    n = re.sub(r"[_\-]+", " ", n)
    return re.sub(r"\s+", " ", n)


def build_column_map(header: Iterable[str]) -> dict[str, str]:
    """Map canonical key -> actual column name found in the header (first alias match wins)."""
    norm = {normalise_key(h): h for h in header if h is not None}
    out: dict[str, str] = {}
    for key, aliases in COLUMN_ALIASES.items():
        for a in aliases:
            if a in norm:
                out[key] = norm[a]
                break
    return out


def parse_time(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        dt = v
    elif isinstance(v, (int, float)):
        dt = datetime.fromtimestamp(v / 1000 if v > 1e11 else v, tz=timezone.utc)
    else:
        s = str(v).strip()
        if not s:
            return None
        s = s.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(s, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=EAT)
    return dt.astimezone(EAT)


def to_float(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.lower() in ("nan", "null", "none", "na", "n/a", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _rain(r1: float | None, r2: float | None) -> float | None:
    vals = [v for v in (r1, r2) if v is not None]
    if not vals:
        return None
    if RAIN_GAUGE_STRATEGY == "gauge1":
        return r1 if r1 is not None else r2
    if RAIN_GAUGE_STRATEGY == "mean":
        return sum(vals) / len(vals)
    return max(vals)


def normalise_rows(rows: Iterable[dict[str, Any]], drop_unhealthy: bool = True) -> list[RawRecord]:
    """Map arbitrary dict rows (CSV DictReader or API JSON objects) to RawRecords, de-duplicated and sorted."""
    rows = list(rows)
    if not rows:
        return []
    cmap = build_column_map(rows[0].keys())
    if "time" not in cmap:
        raise ValueError(f"No time column found. Columns: {list(rows[0].keys())[:20]}")

    def get(row: dict[str, Any], key: str) -> Any:
        col = cmap.get(key)
        return row.get(col) if col else None

    seen: set[datetime] = set()
    out: list[RawRecord] = []
    for row in rows:
        t = parse_time(get(row, "time"))
        if t is None or t in seen:
            continue
        health_raw = get(row, "health")
        health = int(to_float(health_raw)) if to_float(health_raw) is not None else None
        if drop_unhealthy and health is not None and health != 0:
            continue
        seen.add(t)
        vis, ir = to_float(get(row, "vis")), to_float(get(row, "ir"))
        light = None if vis is None and ir is None else (vis or 0.0) + (ir or 0.0)
        out.append(
            RawRecord(
                time=t,
                health=health,
                battery_v=to_float(get(row, "battery_v")),
                rain_mm=_rain(to_float(get(row, "rain1")), to_float(get(row, "rain2"))),
                temp=to_float(get(row, "temp")),
                rh=to_float(get(row, "rh")),
                wind=to_float(get(row, "wind")),
                heat_index=to_float(get(row, "heat_index")),
                wet_bulb=to_float(get(row, "wet_bulb")),
                wbgt=to_float(get(row, "wbgt")),
                light=light,
                uv=to_float(get(row, "uv")),
                soil=to_float(get(row, "soil")),
            )
        )
    out.sort(key=lambda r: r["time"])
    return out


def parse_geocsv_text(text: str, drop_unhealthy: bool = True) -> list[RawRecord]:
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return []
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    return normalise_rows(reader, drop_unhealthy=drop_unhealthy)


def parse_geocsv(path: str | Path, drop_unhealthy: bool = True) -> list[RawRecord]:
    return parse_geocsv_text(Path(path).read_text(encoding="utf-8-sig"), drop_unhealthy=drop_unhealthy)


def rain_from_cumulative(records: list[RawRecord]) -> list[RawRecord]:
    """If the gauges report a running total, convert to per-interval mm (resets -> take the new value)."""
    prev: float | None = None
    out: list[RawRecord] = []
    for r in records:
        cur = r.get("rain_mm")
        if cur is None:
            out.append(r)
            continue
        inc = cur if prev is None else (cur - prev if cur >= prev else cur)
        prev = cur
        out.append({**r, "rain_mm": max(0.0, inc)})
    return out
