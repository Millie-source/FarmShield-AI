"""Weather provider registry.

WEATHER_PROVIDER = conduit_api | conduit_csv | scenario   (default conduit_csv; legacy 'mock' = scenario,
legacy 'conduit' = conduit_api).  Every provider degrades: conduit_api -> conduit_csv -> scenario.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.engine.types import Reading

from .base import STATION, WeatherProvider, coverage
from .conduit_api import ConduitApiClient, ConduitApiProvider, ConduitError
from .conduit_csv import ConduitCsvProvider
from .scenario import MockWeatherProvider, ScenarioWeatherProvider, scenario_state

__all__ = [
    "STATION", "ConduitApiProvider", "ConduitApiClient", "ConduitError", "WeatherProvider", "ScenarioWeatherProvider", "MockWeatherProvider", "ConduitCsvProvider",
    "scenario_state", "get_weather_provider", "describe", "coverage", "reset_provider_cache", "backend_path",
]

BACKEND_DIR = Path(__file__).resolve().parents[3]


def backend_path(p: str | Path) -> Path:
    p = Path(p)
    return p if p.is_absolute() else BACKEND_DIR / p


def _csv_provider() -> ConduitCsvProvider:
    s = get_settings()
    return ConduitCsvProvider(backend_path(s.conduit_daily_csv), backend_path(s.conduit_raw_csv))


@lru_cache
def _default_provider() -> WeatherProvider:
    s = get_settings()
    scenario_state.set(s.default_scenario if s.default_scenario in ("normal", "dry_spell", "heavy_rain") else "normal")
    kind = s.weather_provider.lower().strip()
    if kind in ("scenario", "mock"):
        return ScenarioWeatherProvider()
    if kind in ("conduit_api", "conduit"):
        return ConduitApiProvider.from_settings(s, fallback=_csv_provider())
    return _csv_provider()


def reset_provider_cache() -> None:
    _default_provider.cache_clear()


def get_weather_provider(scenario: str | None = None) -> WeatherProvider:
    """Return the configured provider; an explicit ``scenario`` forces a synthetic replay of that scenario."""
    if scenario:
        return ScenarioWeatherProvider(scenario)
    return _default_provider()


def describe(provider: WeatherProvider, readings: list[Reading]) -> tuple[list[str], dict]:
    """(data_sources, data_coverage) for a set of readings fetched from ``provider``."""
    return provider.data_sources(readings), coverage(readings)
