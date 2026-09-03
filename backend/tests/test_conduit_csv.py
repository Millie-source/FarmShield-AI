"""ConduitCsvProvider (real station file + synthetic backfill padding) and the replay clock API."""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

TEST_DB = Path(__file__).resolve().parent / "_test_farmshield.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["WEATHER_PROVIDER"] = "mock"
os.environ["DEFAULT_SCENARIO"] = "normal"
os.environ["SMS_SENDER"] = "console"
os.environ["GEMINI_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import engine  # noqa: E402
from app.ingest import resample  # noqa: E402
from app.main import app  # noqa: E402
from app.providers import weather as registry  # noqa: E402
from app.providers.weather import ConduitCsvProvider, coverage  # noqa: E402
from app.services.clock import replay_clock  # noqa: E402
from tests.test_ingest import make_geocsv  # noqa: E402

TODAY = date(2026, 9, 3)


def _daily_csv(tmp_path: Path, days: int = 5, end: date = TODAY) -> Path:
    from app.ingest import geocsv

    raw = tmp_path / "conduit_raw.csv"
    raw.write_text(make_geocsv(days=days, start=end - timedelta(days=days - 1)))
    rows = resample.daily(geocsv.parse_geocsv(raw))
    return resample.write_daily_csv(rows, tmp_path / "conduit_daily.csv")


def test_pads_short_history_with_synthetic_normal(tmp_path):
    p = ConduitCsvProvider(_daily_csv(tmp_path, days=5))
    hist = p.get_history(-1.1, 37.0, days=30, end=TODAY)
    assert len(hist) == 30
    assert [r.date for r in hist] == [TODAY - timedelta(days=29 - i) for i in range(30)]  # contiguous
    cov = coverage(hist)
    assert cov["real_days"] == 5 and cov["synthetic_days"] == 25 and cov["to"] == "2026-09-03"
    assert cov["station"].startswith("JKUAT Conduit@Empathy1")
    assert all(r.synthetic for r in hist[:25]) and not any(r.synthetic for r in hist[25:])
    assert p.source_id() == "conduit_csv"
    assert p.data_sources(hist) == ["conduit_csv", "synthetic:normal (backfill)"]


def test_no_padding_when_enough_real_days(tmp_path):
    p = ConduitCsvProvider(_daily_csv(tmp_path, days=8))
    hist = p.get_history(-1.1, 37.0, days=7, end=TODAY)
    assert len(hist) == 7 and not any(r.synthetic for r in hist)
    assert p.data_sources(hist) == ["conduit_csv"]


def test_end_date_walks_through_the_file(tmp_path):
    p = ConduitCsvProvider(_daily_csv(tmp_path, days=8))
    early = p.get_history(-1.1, 37.0, days=30, end=TODAY - timedelta(days=5))
    assert coverage(early)["real_days"] == 3 and early[-1].date == TODAY - timedelta(days=5)


def test_missing_file_falls_back_to_scenario(tmp_path):
    p = ConduitCsvProvider(tmp_path / "nope.csv")
    hist = p.get_history(-1.1, 37.0, days=30, end=TODAY)
    assert len(hist) == 30 and all(r.synthetic for r in hist)
    assert p.source_id() == "scenario:normal (synthetic) (conduit_csv missing)"
    assert p.scenario == "normal"


def test_raw_csv_is_ingested_when_daily_missing(tmp_path):
    raw = tmp_path / "conduit_raw.csv"
    raw.write_text(make_geocsv(days=3, start=TODAY - timedelta(days=2)))
    p = ConduitCsvProvider(tmp_path / "conduit_daily.csv", raw)
    assert p.available and (tmp_path / "conduit_daily.csv").exists()
    assert p.date_range() == (TODAY - timedelta(days=2), TODAY)


# ------------------------------------------------------------------- API ----
@pytest.fixture(scope="module")
def client(tmp_path_factory):
    engine.dispose()
    if TEST_DB.exists():
        TEST_DB.unlink()
    settings = get_settings()
    tmp = tmp_path_factory.mktemp("conduit")
    daily = _daily_csv(tmp, days=10, end=date.today())
    old = (settings.weather_provider, settings.conduit_daily_csv)
    settings.weather_provider, settings.conduit_daily_csv = "conduit_csv", str(daily)
    registry.reset_provider_cache()
    with TestClient(app) as c:
        yield c
    replay_clock.reset()
    settings.weather_provider, settings.conduit_daily_csv = old
    registry.reset_provider_cache()
    engine.dispose()
    try:
        TEST_DB.unlink()
    except OSError:
        pass


def test_assessment_reports_real_and_synthetic_days(client):
    d = client.post("/farms/1/assess").json()
    assert d["data_sources"] == ["conduit_csv", "synthetic:normal (backfill)"]
    assert d["data_coverage"]["real_days"] == 10 and d["data_coverage"]["synthetic_days"] == 20
    assert d["scenario"] is None
    w = client.get("/farms/1/weather?days=30").json()
    assert w["data_coverage"]["real_days"] == 10 and w["readings"][-1]["synthetic"] is False and w["readings"][0]["synthetic"] is True


def test_replay_start_step_reset(client):
    st = client.get("/admin/replay").json()
    assert st["active"] is False and st["data_to"] == date.today().isoformat()

    r = client.post("/admin/replay/start", json={})
    assert r.status_code == 200, r.text
    st = r.json()
    start = date.fromisoformat(st["today"])
    assert st["active"] and start == date.today() - timedelta(days=3)  # first day + 6
    assert len(st["reassessed"]) >= 3
    risk = client.get("/farms/1/risk").json()
    assert risk["data_coverage"]["to"] == start.isoformat() and risk["data_coverage"]["real_days"] == 7

    st = client.post("/admin/replay/step", json={"steps": 2}).json()
    assert date.fromisoformat(st["today"]) == start + timedelta(days=2)
    assert st["remaining_days"] == 1
    st = client.post("/admin/replay/step", json={"steps": 5}).json()
    assert st["today"] == date.today().isoformat() and st["remaining_days"] == 0  # clamped to last station day

    st = client.post("/admin/replay/reset").json()
    assert st["active"] is False and st["today"] == date.today().isoformat()
    assert client.post("/admin/replay/step", json={}).status_code == 409


def test_partner_trigger_includes_coverage(client):
    body = {"farm_id": 1, "policy": {"type": "drought", "window_days": 7, "rainfall_threshold_mm": 30}}
    d = client.post("/api/v1/insurance/check-trigger", json=body, headers={"X-API-Key": "fs_demo_acme_insurance_2026"}).json()
    assert d["data_sources"][0] == "conduit_csv" and d["data_coverage"]["real_days"] == 10
