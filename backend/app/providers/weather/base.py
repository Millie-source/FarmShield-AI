"""WeatherProvider interface: anything that can give daily readings for a lat/lon up to a date."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any

from app.engine.types import Reading

STATION = "JKUAT Conduit@Empathy1 (sensor 61)"


class WeatherProvider(ABC):
    name: str = "base"

    @abstractmethod
    def get_history(self, lat: float, lon: float, days: int = 30, end: date | None = None) -> list[Reading]:
        """Daily readings, oldest first, ending on ``end`` (default today / replay clock) or the latest available day."""

    def get_latest(self, lat: float, lon: float, end: date | None = None) -> Reading:
        hist = self.get_history(lat, lon, days=1, end=end)
        if not hist:
            raise LookupError(f"{self.name}: no readings available")
        return hist[-1]

    @abstractmethod
    def source_id(self) -> str:
        """Short identifier recorded on every assessment, e.g. 'conduit_csv', 'scenario:dry_spell'."""

    def data_sources(self, readings: list[Reading]) -> list[str]:
        """Everything that contributed to ``readings`` (primary source + any synthetic backfill)."""
        srcs = [self.source_id()]
        real = sum(1 for r in readings if not r.synthetic)
        synth = len(readings) - real
        if real and synth:
            srcs.append("synthetic:normal (backfill)")
        return srcs

    @property
    def scenario(self) -> str | None:
        return None


def coverage(readings: list[Reading]) -> dict[str, Any]:
    """data_coverage block: how much of the window is real station data vs. synthetic."""
    if not readings:
        return {"real_days": 0, "synthetic_days": 0, "from": None, "to": None, "station": STATION}
    ordered = sorted(readings, key=lambda r: r.date)
    real = sum(1 for r in ordered if not r.synthetic)
    return {
        "real_days": real,
        "synthetic_days": len(ordered) - real,
        "from": ordered[0].date.isoformat(),
        "to": ordered[-1].date.isoformat(),
        "station": STATION,
    }
