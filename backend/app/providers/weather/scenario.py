"""ScenarioWeatherProvider: replays the SYNTHETIC demo scenarios (normal | dry_spell | heavy_rain).

Used for the live "flip the weather" pitch moment and for tests - it is not station data and every
reading is flagged ``synthetic``.  A process-wide scenario switch lets the demo flip conditions;
individual calls can still override it.
"""
from __future__ import annotations

import threading
from datetime import date

from app.engine.sample_data import SCENARIOS, load_sample_readings
from app.engine.types import Reading

from .base import WeatherProvider


class ScenarioState:
    """Thread-safe holder for the active demo scenario."""

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


class ScenarioWeatherProvider(WeatherProvider):
    name = "scenario"

    def __init__(self, scenario: str | None = None) -> None:
        self._override = scenario

    @property
    def scenario(self) -> str:
        return self._override or scenario_state.current

    def source_id(self) -> str:
        return f"scenario:{self.scenario} (synthetic)"

    def get_history(self, lat: float, lon: float, days: int = 30, end: date | None = None) -> list[Reading]:
        readings = load_sample_readings(self.scenario, end_date=end or date.today())
        return readings[-days:] if days < len(readings) else readings


MockWeatherProvider = ScenarioWeatherProvider  # backwards-compatible alias
