"""Gemini adapter for advice text (google-genai SDK).

Returns ``None`` whenever it cannot produce advice - no key, SDK missing, network
error, bad JSON - and the caller keeps the rule-based fallback.  Scoring never
touches the LLM; Gemini only rewrites the structured assessment as farmer-friendly
English + Kiswahili text.

Model: ``GEMINI_MODEL`` (default gemini-3.1-flash-lite). ``gemini-flash-latest`` is
refused because its free-tier quota 429s constantly during demos.
"""
from __future__ import annotations

import json
import logging
import re

from app.config import get_settings
from app.engine.types import Reading, RiskAssessment, TriggerResult
from app.services.advisor import SMS_LIMIT, Advice, _sms

log = logging.getLogger("farmshield.gemini")

BANNED_MODELS = {"gemini-flash-latest", "gemini-pro-latest"}
DEFAULT_MODEL = "gemini-3.1-flash-lite"
TIMEOUT_MS = 8000

SYSTEM = (
    "You are FarmShield, an agronomy advisor for smallholder farmers in Kiambu County, Kenya. "
    "You receive a structured, already-computed climate risk assessment. Do NOT change or question the scores. "
    "Write practical, specific advice a farmer can act on this week. Plain words, no jargon, no markdown. "
    "Return ONLY a JSON object with keys: en (2-3 sentences English), sw (2-3 sentences Kiswahili), "
    f"sms_en (<= {SMS_LIMIT} chars, starts with 'FarmShield:'), sms_sw (<= {SMS_LIMIT} chars, starts with 'FarmShield:')."
)


def _resolve_model(name: str) -> str:
    name = (name or "").strip() or DEFAULT_MODEL
    if name in BANNED_MODELS:
        log.warning("GEMINI_MODEL=%s is not allowed (quota); using %s", name, DEFAULT_MODEL)
        return DEFAULT_MODEL
    return name


def _prompt(a: RiskAssessment, trigger: TriggerResult, farm_name: str, readings: list[Reading], fallback: Advice) -> str:
    recent = sorted(readings, key=lambda r: r.date)[-7:]
    facts = {
        "farm_name": farm_name,
        "crop": a.crop,
        "stage": a.stage.name,
        "day_after_planting": a.stage.day_after_planting,
        "stage_is_critical": a.stage.is_critical,
        "water_need_mm_week": a.stage.water_need_mm_week,
        "overall": {"score": a.overall.score, "level": a.overall.level},
        "sub_scores": {k: {"score": v.score, "level": v.level, "reasons": v.reasons} for k, v in a.sub_scores.items()},
        "insurance_trigger": {"triggered": trigger.triggered, "rule": trigger.rule, "evidence": trigger.evidence},
        "last_7_days": [
            {"date": r.date.isoformat(), "rain_mm": r.rainfall_mm, "tmax_c": r.temp_max_c, "soil_pct": r.soil_moisture_pct} for r in recent
        ],
        "reference_advice_en": fallback.en,
    }
    return "ASSESSMENT:\n" + json.dumps(facts, ensure_ascii=False, indent=1)


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def gemini_advice(
    a: RiskAssessment, trigger: TriggerResult, farm_name: str, readings: list[Reading], fallback: Advice
) -> Advice | None:
    settings = get_settings()
    if not settings.gemini_api_key:
        return None
    model = _resolve_model(settings.gemini_model)
    try:
        from google import genai  # lazy: SDK optional
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))
        resp = client.models.generate_content(
            model=model,
            contents=_prompt(a, trigger, farm_name, readings, fallback),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM,
                response_mime_type="application/json",
                temperature=0.4,
                max_output_tokens=600,
            ),
        )
        data = _extract_json(resp.text or "")
    except Exception as exc:  # noqa: BLE001 - caller falls back
        log.warning("Gemini call failed (%s: %s); using rule-based advice", type(exc).__name__, exc)
        return None

    if not isinstance(data, dict) or not data.get("en") or not data.get("sw"):
        log.warning("Gemini returned unusable JSON; using rule-based advice")
        return None
    return Advice(
        en=" ".join(str(data["en"]).split()),
        sw=" ".join(str(data["sw"]).split()),
        source="gemini",
        sms_en=_sms(str(data.get("sms_en") or fallback.sms_en)),
        sms_sw=_sms(str(data.get("sms_sw") or fallback.sms_sw)),
    )
