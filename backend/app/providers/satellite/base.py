"""SatelliteProvider slot (stretch goal). Default implementation returns None so the
engine falls back to weather-derived crop health. Swap in a Sentinel-2 / MODIS NDVI
client later without touching the engine or routers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date


class SatelliteProvider(ABC):
    name: str = "base"

    @abstractmethod
    def get_ndvi(self, lat: float, lon: float, on: date | None = None) -> float | None:
        """Latest NDVI (0-1) for the location, or None if unavailable."""

    def source_id(self) -> str | None:
        return None


class NullSatelliteProvider(SatelliteProvider):
    name = "none"

    def get_ndvi(self, lat: float, lon: float, on: date | None = None) -> float | None:
        return None


class MockSatelliteProvider(SatelliteProvider):
    """Deterministic NDVI for demos: scenario-dependent canopy vigour."""

    name = "mock-ndvi"
    NDVI = {"normal": 0.62, "dry_spell": 0.38, "heavy_rain": 0.55}

    def __init__(self, scenario_getter) -> None:
        self._scenario = scenario_getter

    def get_ndvi(self, lat: float, lon: float, on: date | None = None) -> float | None:
        return self.NDVI.get(self._scenario(), 0.55)

    def source_id(self) -> str | None:
        return f"satellite:mock-ndvi:{self._scenario()}"


def get_satellite_provider() -> SatelliteProvider:
    return NullSatelliteProvider()
