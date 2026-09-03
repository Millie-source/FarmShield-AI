"""Weather provider registry: pick mock or Conduit from settings."""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings

from .base import WeatherProvider
from .conduit import ConduitWeatherProvider
from .mock import MockWeatherProvider, scenario_state

__all__ = ["WeatherProvider", "MockWeatherProvider", "ConduitWeatherProvider", "scenario_state", "get_weather_provider"]


@lru_cache
def _default_provider() -> WeatherProvider:
    s = get_settings()
    scenario_state.set(s.default_scenario if s.default_scenario in ("normal", "dry_spell", "heavy_rain") else "normal")
    if s.weather_provider.lower() == "conduit":
        return ConduitWeatherProvider(s.conduit_api_url, s.conduit_api_key, fallback=MockWeatherProvider())
    return MockWeatherProvider()


def get_weather_provider(scenario: str | None = None) -> WeatherProvider:
    """Return the configured provider; an explicit ``scenario`` forces a mock replay of that scenario."""
    if scenario:
        return MockWeatherProvider(scenario)
    return _default_provider()
