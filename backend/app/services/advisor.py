"""Advice generation: structured risk -> farmer-friendly text (EN + SW).

Rule-based templates are the always-available fallback; ``generate_advice`` tries
Gemini first (when GEMINI_API_KEY is set) and degrades to the templates on any
failure.  The scoring itself is never delegated to the LLM.

NOTE: lives in services/ rather than engine/ so that engine/ stays stdlib-only.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import timedelta

from app.engine.crops import get_crop
from app.engine.types import Reading, RiskAssessment, TriggerResult

log = logging.getLogger("farmshield.advisor")

SMS_LIMIT = 160

STAGE_SW = {
    "establishment": "kuota",
    "vegetative": "kukua majani",
    "flowering": "kutoa maua",
    "grain_fill": "kujaza punje",
    "pod_fill": "kujaza maganda",
    "tuber_initiation": "kuanza viazi",
    "tuber_bulking": "kunenepa viazi",
    "fruit_fill": "kujaza matunda",
    "ripening": "kuiva",
    "leaf_harvest": "kuvuna majani",
    "maturity": "kukomaa",
}
CROP_SW = {"maize": "mahindi", "beans": "maharagwe", "potatoes": "viazi", "tomatoes": "nyanya", "kale": "sukuma wiki"}
LEVEL_SW = {"LOW": "CHINI", "MEDIUM": "WASTANI", "HIGH": "JUU"}


@dataclass
class Advice:
    en: str
    sw: str
    source: str  # gemini | fallback
    sms_en: str
    sms_sw: str

    def to_dict(self) -> dict:
        return asdict(self)


def _facts(readings: list[Reading], a: RiskAssessment) -> dict:
    ordered = sorted(readings, key=lambda r: r.date)
    end = ordered[-1].date
    last7 = [r for r in ordered if r.date >= end - timedelta(days=6)]
    last3 = [r for r in ordered if r.date >= end - timedelta(days=2)]
    return {
        "rain7": round(sum(r.rainfall_mm for r in last7)),
        "rain72": round(sum(r.rainfall_mm for r in last3)),
        "need": round(a.stage.water_need_mm_week),
        "tmax": round(max(r.temp_max_c for r in last7), 1),
        "thr": round(a.stage.max_temp_c),
        "soil": round(ordered[-1].soil_moisture_pct),
    }


def _dominant(a: RiskAssessment) -> tuple[str, int]:
    hazards = {"drought": a.drought.score, "flood": a.flood.score, "heat": a.heat.score}
    k = max(hazards, key=hazards.get)  # type: ignore[arg-type]
    return k, hazards[k]


def fallback_advice(a: RiskAssessment, trigger: TriggerResult, farm_name: str, readings: list[Reading]) -> Advice:
    f = _facts(readings, a)
    crop_en = get_crop(a.crop).display_name.split(" (")[0].lower()
    crop_sw = CROP_SW.get(a.crop, a.crop)
    stage_en = a.stage.name.replace("_", " ")
    stage_sw = STAGE_SW.get(a.stage.name, stage_en)
    hazard, hscore = _dominant(a)
    level = a.overall.level
    score = a.overall.score

    if level == "LOW":
        en = (
            f"Conditions look good for your {crop_en} at the {stage_en} stage. Rainfall and temperature are within the "
            f"range the crop needs. Keep to your normal schedule and scout for pests and disease once a week."
        )
        sw = (
            f"Hali ni nzuri kwa {crop_sw} yako katika hatua ya {stage_sw}. Mvua na joto viko ndani ya kiwango kinachohitajika. "
            f"Endelea na ratiba yako ya kawaida na kagua wadudu na magonjwa mara moja kwa wiki."
        )
        act_en, act_sw = "Conditions OK. Keep normal schedule.", "Hali nzuri. Endelea kama kawaida."
    elif hazard == "drought":
        if level == "HIGH":
            en = (
                f"Your {crop_en} is at the {stage_en} stage and has had only {f['rain7']} mm of rain in the last 7 days "
                f"against a need of about {f['need']} mm. Low rainfall now can significantly cut yield. Irrigate within "
                f"24-48 hours if you can, and hold off fertiliser until rainfall improves."
            )
            sw = (
                f"{crop_sw.capitalize()} yako iko katika hatua ya {stage_sw} na imepata mvua ya mm {f['rain7']} tu katika siku 7 "
                f"zilizopita, ikihitaji takriban mm {f['need']}. Ukosefu wa mvua sasa unaweza kupunguza mavuno sana. Mwagilia "
                f"ndani ya saa 24-48 ukiweza, na usiweke mbolea hadi mvua irudi."
            )
            act_en, act_sw = "Irrigate in 24-48h. Hold fertiliser.", "Mwagilia ndani ya saa 24-48. Usiweke mbolea."
        else:
            en = (
                f"Your {crop_en} is at the {stage_en} stage. Rainfall ({f['rain7']} mm this week) is running below the "
                f"{f['need']} mm the crop needs. Plan irrigation in the next 2-3 days, mulch to keep soil moisture, and "
                f"delay top-dressing until after rain."
            )
            sw = (
                f"{crop_sw.capitalize()} yako iko katika hatua ya {stage_sw}. Mvua (mm {f['rain7']} wiki hii) iko chini ya mm "
                f"{f['need']} inayohitajika. Panga kumwagilia ndani ya siku 2-3, weka matandazo kuhifadhi unyevu, na "
                f"chelewesha mbolea ya juu hadi mvua inyeshe."
            )
            act_en, act_sw = "Plan irrigation in 2-3 days. Mulch.", "Panga kumwagilia siku 2-3. Weka matandazo."
    elif hazard == "flood":
        en = (
            f"Heavy rain ({f['rain72']} mm in the last 3 days) is saturating your {crop_en} field at the {stage_en} stage. "
            f"Open drainage channels now, do not apply fertiliser (it will wash away), and check for fungal disease and "
            f"yellowing leaves over the next week."
        )
        sw = (
            f"Mvua kubwa (mm {f['rain72']} katika siku 3) inalowesha shamba lako la {crop_sw} katika hatua ya {stage_sw}. "
            f"Fungua mifereji ya maji sasa, usiweke mbolea (itasombwa), na kagua magonjwa ya fangasi na majani ya njano wiki ijayo."
        )
        act_en, act_sw = "Open drainage. No fertiliser. Watch disease.", "Fungua mifereji. Usiweke mbolea."
    else:  # heat
        en = (
            f"Temperatures reached {f['tmax']}°C this week, above the {f['thr']}°C your {crop_en} tolerates during "
            f"{stage_en}. Irrigate early morning or evening to cool the crop, avoid spraying in the midday heat, and "
            f"keep the soil covered with mulch."
        )
        sw = (
            f"Joto lilifika {f['tmax']}°C wiki hii, zaidi ya {f['thr']}°C ambayo {crop_sw} yako inavumilia wakati wa "
            f"{stage_sw}. Mwagilia asubuhi au jioni, epuka kupulizia dawa mchana, na funika udongo kwa matandazo."
        )
        act_en, act_sw = "Irrigate AM/PM. Avoid midday spraying.", "Mwagilia asubuhi/jioni. Epuka dawa mchana."

    if trigger.triggered:
        ev = trigger.evidence
        if trigger.rule == "drought_rainfall_deficit":
            en += (
                f" Rainfall over the last {ev['window_days']} days ({ev['rainfall_total_mm']} mm) is below the "
                f"{ev['threshold_mm']:.0f} mm insurance trigger - your cover may pay out. Contact your insurer or SACCO."
            )
            sw += (
                f" Mvua ya siku {ev['window_days']} zilizopita (mm {ev['rainfall_total_mm']}) iko chini ya kiwango cha bima "
                f"cha mm {ev['threshold_mm']:.0f} - bima yako inaweza kulipa. Wasiliana na bima au SACCO yako."
            )
        else:
            en += " Weather has crossed an insurance trigger - contact your insurer or SACCO."
            sw += " Hali ya hewa imevuka kiwango cha bima - wasiliana na bima au SACCO yako."
        act_en += " Insurance trigger met."
        act_sw += " Bima inaweza kulipa."

    sms_en = _sms(f"FarmShield: {farm_name} risk {level} ({score}/100). {crop_en.capitalize()} {stage_en}. {act_en}")
    sms_sw = _sms(f"FarmShield: {farm_name} hatari {LEVEL_SW[level]} ({score}/100). {crop_sw.capitalize()} {stage_sw}. {act_sw}")
    return Advice(en=en, sw=sw, source="fallback", sms_en=sms_en, sms_sw=sms_sw)


def _sms(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SMS_LIMIT else text[: SMS_LIMIT - 1].rstrip() + "…"


def generate_advice(a: RiskAssessment, trigger: TriggerResult, farm_name: str, readings: list[Reading]) -> Advice:
    """Gemini when configured, rule-based fallback otherwise. Never raises."""
    fallback = fallback_advice(a, trigger, farm_name, readings)
    try:
        from app.services.gemini import gemini_advice  # imported lazily so a missing SDK never breaks scoring

        result = gemini_advice(a, trigger, farm_name, readings, fallback)
        if result is not None:
            return result
    except Exception as exc:  # noqa: BLE001
        log.warning("Gemini advice unavailable (%s); using rule-based text", exc)
    return fallback
