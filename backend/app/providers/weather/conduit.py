"""ConduitWeatherProvider: adapter for the JKUAT Conduit weather station API.

ASSUMPTION (flagged): the real payload shape has not been shared yet. This adapter
expects ``GET {CONDUIT_API_URL}/readings?lat=..&lon=..&days=N`` returning either a
list or ``{"data": [...]}`` of records like::

    {"timestamp": "2026-09-03T14:00:00Z", "temperature": 31.2, "rainfall": 0.0,
     "humidity": 41, "soil_moisture": 13.5, "solar_radiation": 280, "wind_speed": 3.1}

Sub-daily records are aggregated to daily (max/min temp, summed rain, mean others).
Update ``FIELD_ALIASES`` / ``_parse`` when the real schema arrives - nothing else
needs to change.  Any failure logs a warning and falls back to the mock provider so
the API never 500s because the station is unreachable.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime
from statistics import mean
from typing import Any

import httpx

from app.engine.types import Reading

from .base import WeatherProvider
from .mock import MockWeatherProvider

log = logging.getLogger("farmshield.conduit")

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp", "time", "datetime", "date", "recorded_at", "created_at"),
    "temperature": ("temperature", "temp", "temp_c", "air_temperature"),
    "temp_max": ("temp_max", "temperature_max", "tmax"),
    "temp_min": ("temp_min", "temperature_min", "tmin"),
    "rainfall": ("rainfall", "rain", "precipitation", "rain_mm", "rainfall_mm"),
    "humidity": ("humidity", "relative_humidity", "rh", "humidity_pct"),
    "soil_moisture": ("soil_moisture", "soil_moisture_pct", "soil", "vwc"),
    "solar_radiation": ("solar_radiation", "solar", "radiation", "irradiance"),
    "wind_speed": ("wind_speed", "wind", "wind_ms"),
}


def _pick(rec: dict[str, Any], key: str) -> Any:
    for alias in FIELD_ALIASES[key]:
        if alias in rec and rec[alias] is not None:
            return rec[alias]
    return None


def _to_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return datetime.utcfromtimestamp(v / 1000 if v > 1e11 else v).date()
    s = str(v).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None


def _parse(records: list[dict[str, Any]]) -> list[Reading]:
    by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        d = _to_date(_pick(rec, "timestamp"))
        if d:
            by_day[d].append(rec)

    out: list[Reading] = []
    for d in sorted(by_day):
        recs = by_day[d]
        temps = [float(t) for t in (_pick(r, "temperature") for r in recs) if t is not None]
        tmax_explicit = [float(t) for t in (_pick(r, "temp_max") for r in recs) if t is not None]
        tmin_explicit = [float(t) for t in (_pick(r, "temp_min") for r in recs) if t is not None]
        tmax = max(tmax_explicit) if tmax_explicit else (max(temps) if temps else None)
        tmin = min(tmin_explicit) if tmin_explicit else (min(temps) if temps else None)
        if tmax is None or tmin is None:
            continue
        rain = sum(float(x) for x in (_pick(r, "rainfall") for r in recs) if x is not None)
        hum = [float(x) for x in (_pick(r, "humidity") for r in recs) if x is not None]
        soil = [float(x) for x in (_pick(r, "soil_moisture") for r in recs) if x is not None]
        solar = [float(x) for x in (_pick(r, "solar_radiation") for r in recs) if x is not None]
        wind = [float(x) for x in (_pick(r, "wind_speed") for r in recs) if x is not None]
        out.append(
            Reading(
                date=d,
                rainfall_mm=round(rain, 1),
                temp_max_c=round(tmax, 1),
                temp_min_c=round(tmin, 1),
                humidity_pct=round(mean(hum), 0) if hum else 60.0,
                soil_moisture_pct=round(mean(soil), 1) if soil else None,
                light_index=None if not solar else round(min(1.0, mean(solar) / 1000.0), 2),
                wind_speed_ms=round(mean(wind), 1) if wind else None,
            )
        )
    return out


class ConduitWeatherProvider(WeatherProvider):
    name = "conduit"

    def __init__(self, base_url: str, api_key: str = "", timeout_s: float = 6.0, fallback: WeatherProvider | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.fallback = fallback or MockWeatherProvider()
        self._last_ok = False

    def source_id(self) -> str:
        return "conduit:jkuat" if self._last_ok else f"{self.fallback.source_id()} (conduit unavailable)"

    @property
    def scenario(self) -> str | None:
        return None if self._last_ok else self.fallback.scenario

    def get_history(self, lat: float, lon: float, days: int = 30) -> list[Reading]:
        if not self.base_url:
            log.warning("CONDUIT_API_URL not set; using %s", self.fallback.source_id())
            self._last_ok = False
            return self.fallback.get_history(lat, lon, days)
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                resp = client.get(f"{self.base_url}/readings", params={"lat": lat, "lon": lon, "days": days}, headers=headers)
                resp.raise_for_status()
                payload = resp.json()
            records = payload.get("data", payload.get("readings", payload)) if isinstance(payload, dict) else payload
            readings = _parse(list(records))
            if not readings:
                raise ValueError("Conduit returned no parsable daily readings")
            self._last_ok = True
            return readings[-days:]
        except Exception as exc:  # noqa: BLE001 - degrade gracefully, never 500
            log.warning("Conduit station unreachable (%s); falling back to %s", exc, self.fallback.source_id())
            self._last_ok = False
            return self.fallback.get_history(lat, lon, days)
