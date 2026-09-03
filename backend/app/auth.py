"""Partner authentication: X-API-Key header -> ApiClient row."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.db import get_db

api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    scheme_name="PartnerApiKey",
    description="Partner API key issued to insurers, banks, SACCOs and agribusinesses. Demo keys: "
    "`fs_demo_acme_insurance_2026` (acme-insurance), `fs_demo_harvest_sacco_2026` (harvest-sacco).",
)


def require_api_key(api_key: str | None = Security(api_key_header), db: Session = Depends(get_db)) -> models.ApiClient:
    if not api_key:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    client = db.scalar(select(models.ApiClient).where(models.ApiClient.api_key == api_key, models.ApiClient.active.is_(True)))
    if client is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    client.last_used_at = datetime.now(timezone.utc)
    client.request_count = (client.request_count or 0) + 1
    db.commit()
    return client
