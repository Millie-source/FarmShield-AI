"""FarmShield climate risk engine - pure Python, stdlib only.

Public API:
    derive_stage(crop, planting_date, today) -> Stage
    assess(readings, crop, stage, ndvi=None) -> RiskAssessment
    check_trigger(readings, crop, stage, policy) -> TriggerResult
"""
from .crops import CROPS, CROP_KEYS, get_crop
from .insurance import check_trigger
from .sample_data import SCENARIOS, load_sample_readings
from .scoring import assess
from .stages import derive_stage
from .types import Overall, Policy, Reading, RiskAssessment, Stage, SubScore, TriggerResult, level_for

__all__ = [
    "CROPS", "CROP_KEYS", "get_crop", "check_trigger", "SCENARIOS", "load_sample_readings",
    "assess", "derive_stage", "Overall", "Policy", "Reading", "RiskAssessment", "Stage",
    "SubScore", "TriggerResult", "level_for",
]
