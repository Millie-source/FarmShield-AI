"""Shared fixtures: the three bundled Juja scenarios and a fixed 'today'."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.engine.sample_data import load_sample_readings
from app.engine.types import Reading

TODAY = date(2026, 9, 3)


@pytest.fixture(scope="session")
def today() -> date:
    return TODAY


@pytest.fixture(scope="session")
def normal() -> list[Reading]:
    return load_sample_readings("normal", end_date=TODAY)


@pytest.fixture(scope="session")
def dry_spell() -> list[Reading]:
    return load_sample_readings("dry_spell", end_date=TODAY)


@pytest.fixture(scope="session")
def heavy_rain() -> list[Reading]:
    return load_sample_readings("heavy_rain", end_date=TODAY)


def make_readings(
    days: int = 30,
    rain: float = 0.0,
    tmax: float = 27.0,
    tmin: float = 14.0,
    humidity: float = 60.0,
    soil: float | None = None,
    wbgt: float | None = None,
    heat_index: float | None = None,
    light: float | None = None,
    end: date = TODAY,
) -> list[Reading]:
    """Uniform synthetic series, handy for isolating one variable in a test.
    ``soil`` is a *measured* probe value (None = let the engine model it)."""
    return [
        Reading(
            date=end - timedelta(days=days - 1 - i),
            rainfall_mm=rain,
            temp_max_c=tmax,
            temp_min_c=tmin,
            humidity_pct=humidity,
            soil_moisture_pct=soil,
            wbgt_max_c=wbgt,
            heat_index_max_c=heat_index,
            light_index=light,
            synthetic=True,
        )
        for i in range(days)
    ]
