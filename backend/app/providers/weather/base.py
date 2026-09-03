"""WeatherProvider interface: anything that can give daily readings for a lat/lon."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.engine.types import Reading


class WeatherProvider(ABC):
    name: str = "base"

    @abstractmethod
    def get_history(self, lat: float, lon: float, days: int = 30) -> list[Reading]:
        """Daily readings, oldest first, ending today (or the latest available day)."""

    def get_latest(self, lat: float, lon: float) -> Reading:
        hist = self.get_history(lat, lon, days=1)
        if not hist:
            raise LookupError(f"{self.name}: no readings available")
        return hist[-1]

    @abstractmethod
    def source_id(self) -> str:
        """Short identifier recorded on every assessment, e.g. 'mock:dry_spell' or 'conduit:jkuat'."""

    @property
    def scenario(self) -> str | None:
        return None
