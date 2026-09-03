"""MockWeatherProvider: replays data/sample_readings.json re-dated to end today.

A process-wide scenario switch (normal | dry_spell | heavy_rain) lets the pitch
flip conditions live; individual calls can still override it.
"""
from __future__ import annotations

import threading
from datetime import date

from app.engine.sample_data import SCENARIOS, load_sample_readings
from app.engine.types import Reading

from .base import WeatherProvider


class ScenarioState:
    """Thread-safe holder for the active mock scenario."""

    def __init__(self, initial: str = "normal") -> None:
        self._lock = threading.Lock()
        self._current = initial if initial in SCENARIOS else "normal"

    @property
    def current(self) -> str:
        with self._lock:
            return self._current

    def set(self, scenario: str) -> str:
        if scenario not in SCENARIOS:
            raise ValueError(f"Unknown scenario '{scenario}'. Choose one of {SCENARIOS}")
        with self._lock:
            self._current = scenario
        return scenario


scenario_state = ScenarioState()


class MockWeatherProvider(WeatherProvider):
    name = "mock"

    def __init__(self, scenario: str | None = None) -> None:
        self._override = scenario

    @property
    def scenario(self) -> str:
        return self._override or scenario_state.current

    def source_id(self) -> str:
        return f"mock:{self.scenario}"

    def get_history(self, lat: float, lon: float, days: int = 30) -> list[Reading]:
        readings = load_sample_readings(self.scenario, end_date=date.today())
        return readings[-days:] if days < len(readings) else readings
