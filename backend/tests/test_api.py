"""API tests against an isolated SQLite file (TestClient, mock weather provider)."""
from __future__ import annotations

import os
from pathlib import Path

TEST_DB = Path(__file__).resolve().parent / "_test_farmshield.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["WEATHER_PROVIDER"] = "mock"
os.environ["DEFAULT_SCENARIO"] = "normal"
os.environ["SMS_SENDER"] = "console"
os.environ["GEMINI_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

ACME = {"X-API-Key": "fs_demo_acme_insurance_2026"}
SACCO = {"X-API-Key": "fs_demo_harvest_sacco_2026"}


@pytest.fixture(scope="module")
def client():
    if TEST_DB.exists():
        TEST_DB.unlink()
    with TestClient(app) as c:  # runs lifespan -> creates tables + seeds
        yield c
    try:
        TEST_DB.unlink()
    except OSError:
        pass


# ------------------------------------------------------------------- farms ----
def test_seeded_farms_listed(client):
    r = client.get("/farms")
    assert r.status_code == 200
    farms = r.json()
    assert [f["crop"] for f in farms] == ["maize", "beans", "kale"]
    assert [f["stage"] for f in farms] == ["flowering", "vegetative", "establishment"]


def test_register_farm_runs_first_assessment(client):
    body = {
        "farmer_name": "Test Farmer",
        "phone": "0722000099",
        "language": "en",
        "farm_name": "Test Tomatoes",
        "crop": "tomato",
        "planting_date": "2026-07-20",
        "lat": -1.1,
        "lon": 37.01,
    }
    r = client.post("/farms", json=body)
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["phone"] == "+254722000099"
    assert f["crop"] == "tomatoes"
    assert f["latest_risk"]["overall_score"] >= 0
    client.delete(f"/farms/{f['id']}")


def test_register_farm_rejects_unknown_crop(client):
    r = client.post(
        "/farms",
        json={"farmer_name": "X Y", "phone": "+254700000000", "farm_name": "Bad", "crop": "cassava", "planting_date": "2026-08-01", "lat": -1.1, "lon": 37.0},
    )
    assert r.status_code == 422
    assert "Unknown crop" in r.text


def test_missing_farm_is_404(client):
    assert client.get("/farms/999/risk").status_code == 404


# -------------------------------------------------------------------- risk ----
def test_assess_returns_full_risk_payload(client):
    r = client.post("/farms/1/assess")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["crop"] == "maize" and d["stage"]["name"] == "flowering"
    assert set(d["sub_scores"]) == {"drought", "flood", "heat", "crop_health"}
    for s in d["sub_scores"].values():
        assert s["reasons"]
    assert d["overall"]["label"].endswith("CLIMATE RISK")
    assert d["advice"]["source"] in ("gemini", "fallback")
    assert len(d["advice"]["sms_en"]) <= 160 and len(d["advice"]["sms_sw"]) <= 160
    assert d["data_sources"] == ["mock:normal"]
    assert d["assessed_at"].endswith("Z")


def test_scenario_switch_changes_scores(client):
    base = client.post("/farms/1/assess").json()["overall"]["score"]
    r = client.put("/scenario", json={"scenario": "dry_spell", "reassess": True})
    assert r.status_code == 200
    summaries = r.json()["reassessed"]
    assert len(summaries) >= 3 and all(s is not None for s in summaries)
    dry = client.get("/farms/1/risk").json()
    assert dry["scenario"] == "dry_spell"
    assert dry["overall"]["score"] > base
    assert dry["overall"]["level"] == "HIGH"
    assert dry["insurance_trigger"]["triggered"] is True
    client.put("/scenario", json={"scenario": "normal", "reassess": False})


def test_per_call_scenario_override_does_not_change_global(client):
    assert client.get("/scenario").json()["scenario"] == "normal"
    wet = client.post("/farms/3/assess?scenario=heavy_rain").json()
    assert wet["scenario"] == "heavy_rain"
    assert wet["sub_scores"]["flood"]["level"] == "HIGH"
    assert client.get("/scenario").json()["scenario"] == "normal"


def test_history_is_newest_first(client):
    hist = client.get("/farms/1/risk/history?limit=3").json()
    assert len(hist) >= 2
    assert hist[0]["assessment_id"] > hist[1]["assessment_id"]


def test_weather_history(client):
    r = client.get("/farms/1/weather?days=7&scenario=dry_spell")
    assert r.status_code == 200
    d = r.json()
    assert d["days"] == 7 and d["source"] == "mock:dry_spell"
    assert sum(x["rainfall_mm"] for x in d["readings"]) < 1


# ---------------------------------------------------------------- partners ----
def test_partner_requires_api_key(client):
    r = client.get("/api/v1/risk/1")
    assert r.status_code == 401
    assert r.json()["detail"] == "Missing X-API-Key header"
    r = client.get("/api/v1/risk/1", headers={"X-API-Key": "nope"})
    assert r.status_code == 401
    assert "Invalid" in r.json()["detail"]


def test_partner_risk_and_me(client):
    r = client.get("/api/v1/risk/1", headers=ACME)
    assert r.status_code == 200
    assert r.json()["farm_id"] == 1
    me = client.get("/api/v1/me", headers=ACME).json()
    assert me["client"] == "acme-insurance" and me["request_count"] >= 2


def test_partner_bulk(client):
    r = client.get("/api/v1/risk/bulk?farm_ids=1,2,3,999,abc", headers=SACCO)
    assert r.status_code == 200
    d = r.json()
    assert d["count"] == 3
    assert {e["farm_id"] for e in d["errors"]} == {999, "abc"}
    assert d["summary"]["high_risk"] + d["summary"]["medium_risk"] + d["summary"]["low_risk"] == 3


def test_partner_check_trigger(client):
    body = {"farm_id": 1, "policy": {"type": "drought", "window_days": 21, "rainfall_threshold_mm": 30}, "scenario": "dry_spell"}
    r = client.post("/api/v1/insurance/check-trigger", json=body, headers=ACME)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["triggered"] is True and d["rule"] == "drought_rainfall_deficit"
    assert d["evidence"]["rainfall_total_mm"] < 30
    body["scenario"] = "normal"
    assert client.post("/api/v1/insurance/check-trigger", json=body, headers=ACME).json()["triggered"] is False
    # stage gate: kale at establishment is not critical
    gated = {"farm_id": 3, "policy": {"type": "drought", "window_days": 21, "rainfall_threshold_mm": 30, "critical_stages_only": True}, "scenario": "dry_spell"}
    g = client.post("/api/v1/insurance/check-trigger", json=gated, headers=ACME).json()
    assert g["triggered"] is False and g["evidence"]["stage_gate_blocked"] is True


def test_partner_check_trigger_validates_policy(client):
    body = {"farm_id": 1, "policy": {"type": "heat", "window_days": 14}}
    r = client.post("/api/v1/insurance/check-trigger", json=body, headers=ACME)
    assert r.status_code == 422


def test_openapi_has_descriptions_everywhere(client):
    spec = client.get("/openapi.json").json()
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            assert op.get("summary"), f"{method} {path} missing summary"
    for name in ("RiskOut", "FarmCreate", "TriggerCheckIn", "SubScoreOut"):
        assert "example" in spec["components"]["schemas"][name], name
