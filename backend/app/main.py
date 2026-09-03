"""FarmShield AI - FastAPI application entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import admin, alerts, farms, partners, risk
from app.seed import seed_if_empty
from app.services.assessment import assess_unscored_farms

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("farmshield")
settings = get_settings()

TAGS = [
    {"name": "farms", "description": "Register and manage farmer plots."},
    {"name": "risk", "description": "The Farm Risk Score: explainable drought / flood / heat / crop-health scoring with reasons, insurance trigger and advice."},
    {"name": "alerts", "description": "SMS alerts to farmers (Africa's Talking sandbox or console)."},
    {"name": "partners", "description": "API-key protected endpoints for insurers, banks, SACCOs and agribusinesses. Send `X-API-Key`."},
    {"name": "demo", "description": "Live-demo controls: flip the synthetic weather scenario, or replay the real station file day by day."},
    {"name": "system", "description": "Health and metadata."},
]

DESCRIPTION = """
**Hyperlocal climate risk infrastructure for smallholder farmers in Kenya.**

FarmShield turns readings from the **JKUAT Conduit@Empathy1 weather station** (rain gauges, SHT temperature / humidity,
wind, Heat Index, WBGT, SI1145 light) + crop + growth stage + location into:

* a **Farm Risk Score** - drought, flood, heat-stress and crop-health sub-scores (LOW / MEDIUM / HIGH) and an overall 0-100 score, each backed by human-readable *reasons*;
* **stage-aware advice** for the farmer in English and Kiswahili, delivered by SMS;
* **parametric insurance trigger signals** insurers and SACCOs can act on.

Scoring is deterministic and rule-based (FAO-56 crop water requirements, KALRO crop guides) so every number is auditable.
The station has no soil probe: soil moisture is **modelled** with a Hargreaves ET0 water balance and labelled as such.
Every response carries `data_sources` and `data_coverage` (real station days vs synthetic backfill).
Partners authenticate with an `X-API-Key` header on the `/api/v1` routes.
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    seed_if_empty()
    assess_unscored_farms()
    log.info("FarmShield API ready - provider=%s scenario=%s", settings.weather_provider, settings.default_scenario)
    yield


app = FastAPI(
    title="FarmShield AI",
    version="0.2.0",
    description=DESCRIPTION,
    openapi_tags=TAGS,
    lifespan=lifespan,
    contact={"name": "FarmShield AI - Hack the Weather 2026", "url": "https://github.com/Millie-source/FarmShield-AI"},
    license_info={"name": "MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(farms.router)
app.include_router(risk.router)
app.include_router(risk.scenario_router)
app.include_router(alerts.router)
app.include_router(admin.router)
app.include_router(partners.router)


@app.get("/health", tags=["system"], summary="Liveness check")
def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
        "weather_provider": settings.weather_provider,
        "sms_sender": settings.sms_sender,
        "gemini": bool(settings.gemini_api_key),
    }
