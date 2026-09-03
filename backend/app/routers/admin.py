"""Demo controls: replay the station file day by day so the dashboard visibly updates during the pitch."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.providers.weather import ConduitCsvProvider, get_weather_provider
from app.schemas import ReplayStart, ReplayStateOut, ReplayStep
from app.services.assessment import risk_summary, run_assessment
from app.services.clock import replay_clock

log = logging.getLogger("farmshield.admin")
router = APIRouter(prefix="/admin/replay", tags=["demo"])


def _data_range() -> tuple[date, date] | None:
    p = get_weather_provider()
    inner = getattr(p, "fallback", None)
    for cand in (p, inner):
        if isinstance(cand, ConduitCsvProvider):
            return cand.date_range()
    return None


def _state(db: Session | None = None, reassess: bool = False) -> dict:
    st = replay_clock.state
    rng = _data_range()
    out = {
        **st.to_dict(),
        "data_from": rng[0].isoformat() if rng else None,
        "data_to": rng[1].isoformat() if rng else None,
        "remaining_days": (rng[1] - st.current).days if (rng and st.active and st.current) else None,
        "reassessed": [],
    }
    if reassess and db is not None:
        for farm in db.scalars(select(models.Farm).order_by(models.Farm.id)).all():
            try:
                out["reassessed"].append(risk_summary(run_assessment(db, farm)))
            except Exception as exc:  # noqa: BLE001
                log.warning("Replay re-assessment of farm %s failed: %s", farm.id, exc)
                out["reassessed"].append(None)
    return out


@router.get("", response_model=ReplayStateOut, summary="Replay clock state")
def get_replay() -> dict:
    return _state()


@router.post(
    "/start",
    response_model=ReplayStateOut,
    summary="Start replaying the station file",
    description="Sets a virtual 'today'. Default start = 7 days after the first real station day so the first assessment already has a week of real data. Re-assesses every farm.",
)
def start_replay(body: ReplayStart | None = Body(default=None), db: Session = Depends(get_db)) -> dict:
    body = body or ReplayStart()
    rng = _data_range()
    start = body.start_date
    if start is None:
        if rng is None:
            raise HTTPException(409, detail="No station data loaded (conduit_daily.csv missing) - pass start_date explicitly or add the CSV")
        start = min(rng[0] + timedelta(days=6), rng[1])
    replay_clock.start(start, body.step_days)
    return _state(db, reassess=body.reassess)


@router.post("/step", response_model=ReplayStateOut, summary="Advance the replay clock", description="Moves the virtual today forward by `steps` x step_days (never past the last station day) and re-assesses every farm.")
def step_replay(body: ReplayStep | None = Body(default=None), db: Session = Depends(get_db)) -> dict:
    body = body or ReplayStep()
    rng = _data_range()
    try:
        replay_clock.step(body.steps, until=rng[1] if rng else None)
    except RuntimeError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    return _state(db, reassess=body.reassess)


@router.post("/reset", response_model=ReplayStateOut, summary="Back to real time", description="Deactivates the replay clock and re-assesses every farm against the latest data.")
def reset_replay(db: Session = Depends(get_db)) -> dict:
    replay_clock.reset()
    return _state(db, reassess=True)
