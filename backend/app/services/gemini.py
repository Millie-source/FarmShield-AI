"""Gemini adapter for advice text. Filled in at step 7; returning None means "use fallback"."""
from __future__ import annotations

from app.engine.types import Reading, RiskAssessment, TriggerResult
from app.services.advisor import Advice


def gemini_advice(
    a: RiskAssessment, trigger: TriggerResult, farm_name: str, readings: list[Reading], fallback: Advice
) -> Advice | None:
    return None
