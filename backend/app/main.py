"""FarmShield AI - FastAPI application entrypoint."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="FarmShield AI",
    version="0.1.0",
    description=(
        "Hyperlocal climate risk infrastructure for smallholder farmers in Kenya. "
        "Turns weather station readings + crop + growth stage into an explainable "
        "Farm Risk Score, stage-aware advice and parametric insurance trigger signals."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"], summary="Liveness check")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}
