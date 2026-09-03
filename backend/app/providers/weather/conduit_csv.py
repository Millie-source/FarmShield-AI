"""ConduitCsvProvider: real JKUAT Conduit@Empathy station data from a local file.

Reads ``data/conduit_daily.csv`` (daily aggregates, produced by ``ingest/resample.py`` or the
backfill script).  If only the raw GeoCSV export ``data/conduit_raw.csv`` exists it is ingested
and the daily file written on first use.  When the requested window has fewer real days than
asked for, the *earlier* part of the window is padded with the synthetic ``normal`` scenario
(flagged ``synthetic``) so the engine always sees a full history - responses report exactly how
many days were real via ``data_coverage``.

Replay: pass ``end`` (the replay clock's virtual today) to walk the dashboard through the file.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

from app.engine.types import Reading
from app.ingest import geocsv, resample

from .base import WeatherProvider
from .scenario import ScenarioWeatherProvider

log = logging.getLogger("farmshield.conduit_csv")


def pad_history(real: list[Reading], days: int, end: date, pad: WeatherProvider) -> list[Reading]:
    """Fill the *earlier* part of a ``days``-long window ending on ``end`` with synthetic readings."""
    if len(real) >= days:
        return real[-days:]
    pad_end = (real[0].date - timedelta(days=1)) if real else end
    return pad.get_history(0.0, 0.0, days=days - len(real), end=pad_end) + real


class ConduitCsvProvider(WeatherProvider):
    name = "conduit_csv"

    def __init__(self, daily_csv: str | Path, raw_csv: str | Path | None = None, pad_scenario: str = "normal") -> None:
        self.daily_csv = Path(daily_csv)
        self.raw_csv = Path(raw_csv) if raw_csv else None
        self.pad = ScenarioWeatherProvider(pad_scenario)
        self._cache: tuple[float, list[Reading]] | None = None
        self._last_real = 0

    # ------------------------------------------------------------- loading ----
    def _mtime(self) -> float:
        if self.daily_csv.exists():
            return self.daily_csv.stat().st_mtime
        if self.raw_csv and self.raw_csv.exists():
            return self.raw_csv.stat().st_mtime
        return -1.0

    def rebuild_daily(self) -> int:
        """Ingest the raw GeoCSV export and (re)write the daily CSV. Returns the number of daily rows."""
        if not self.raw_csv or not self.raw_csv.exists():
            return 0
        rows = resample.daily(geocsv.parse_geocsv(self.raw_csv))
        resample.write_daily_csv(rows, self.daily_csv)
        log.info("Built %s from %s: %d daily rows", self.daily_csv.name, self.raw_csv.name, len(rows))
        self._cache = None
        return len(rows)

    def all_readings(self) -> list[Reading]:
        m = self._mtime()
        if self._cache and self._cache[0] == m:
            return self._cache[1]
        if not self.daily_csv.exists() and self.raw_csv and self.raw_csv.exists():
            self.rebuild_daily()
            m = self._mtime()
        readings = resample.to_readings(resample.read_daily_csv(self.daily_csv)) if self.daily_csv.exists() else []
        self._cache = (m, readings)
        return readings

    @property
    def available(self) -> bool:
        return bool(self.all_readings())

    def date_range(self) -> tuple[date, date] | None:
        r = self.all_readings()
        return (r[0].date, r[-1].date) if r else None

    # ------------------------------------------------------------- history ----
    def get_history(self, lat: float, lon: float, days: int = 30, end: date | None = None) -> list[Reading]:
        end = end or date.today()
        real = [r for r in self.all_readings() if r.date <= end][-days:]
        self._last_real = len(real)
        return pad_history(real, days, end, self.pad)  # earlier part of the window <- synthetic 'normal'

    def source_id(self) -> str:
        if self._last_real == 0 and not self.available:
            return f"{self.pad.source_id()} (conduit_csv missing)"
        return "conduit_csv"

    @property
    def scenario(self) -> str | None:
        return self.pad.scenario if not self.available else None
