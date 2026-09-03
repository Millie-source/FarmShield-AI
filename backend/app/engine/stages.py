"""Derive the current growth stage of a crop from its planting date."""
from __future__ import annotations

from datetime import date

from .crops import get_crop
from .types import Stage


def derive_stage(crop: str, planting_date: date, today: date | None = None) -> Stage:
    """Walk the crop calendar and return the stage containing ``today``.

    Day 0 is the planting day.  Stage boundaries are inclusive of the new stage
    (maize establishment = 20 days -> day 19 is establishment, day 20 vegetative).
    Past the end of the calendar the crop is clamped to its final stage.
    """
    spec = get_crop(crop)
    today = today or date.today()
    dap = (today - planting_date).days
    if dap < 0:
        raise ValueError(f"planting_date {planting_date} is after today {today}")

    cumulative = 0
    for index, s in enumerate(spec.stages):
        if dap < cumulative + s.days:
            day_in_stage = dap - cumulative
            break
        cumulative += s.days
    else:  # beyond season length -> final stage
        index = len(spec.stages) - 1
        s = spec.stages[index]
        day_in_stage = s.days

    is_critical = s.sensitivity >= 0.8
    return Stage(
        crop=spec.key,
        name=s.name,
        day_after_planting=dap,
        day_in_stage=day_in_stage,
        stage_length_days=s.days,
        season_length_days=spec.season_length_days,
        water_need_mm_week=s.water_need_mm_week,
        sensitivity=s.sensitivity,
        max_temp_c=spec.flowering_max_temp_c if is_critical else spec.max_temp_c,
        index=index,
    )
