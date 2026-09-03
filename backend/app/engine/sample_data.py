"""Loader for the bundled 30-day Juja SYNTHETIC scenarios (normal / dry_spell / heavy_rain).

These exist for the live "flip the weather" demo and for tests; real station data comes
from the Conduit providers.  Every Reading is flagged ``synthetic=True``.

Used by the engine tests, the validation notebook and the backend MockProvider.
Stdlib only.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .types import Reading

SCENARIOS: tuple[str, ...] = ("normal", "dry_spell", "heavy_rain")
DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "sample_readings.json"


def load_raw(path: Path | None = None) -> dict:
    return json.loads((path or DEFAULT_PATH).read_text(encoding="utf-8"))


def load_sample_readings(
    scenario: str = "normal",
    end_date: date | None = None,
    path: Path | None = None,
) -> list[Reading]:
    """Return 30 daily readings for ``scenario`` ending on ``end_date`` (default: the file's base_date).

    Dates are re-based so the mock provider can replay the same shape as "the last 30 days".
    """
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario '{scenario}'. Choose one of {SCENARIOS}")
    raw = load_raw(path)
    base = end_date or date.fromisoformat(raw["base_date"])
    out: list[Reading] = []
    for row in raw["scenarios"][scenario]:
        out.append(
            Reading(
                date=base + timedelta(days=int(row["day_offset"])),
                rainfall_mm=float(row["rainfall_mm"]),
                temp_max_c=float(row["temp_max_c"]),
                temp_min_c=float(row["temp_min_c"]),
                humidity_pct=float(row["humidity_pct"]),
                wind_speed_ms=row.get("wind_speed_ms"),
                wind_gust_ms=row.get("wind_gust_ms"),
                heat_index_max_c=row.get("heat_index_max_c"),
                wbgt_max_c=row.get("wbgt_max_c"),
                light_index=row.get("light_index"),
                synthetic=True,
            )
        )
    out.sort(key=lambda r: r.date)
    return out
