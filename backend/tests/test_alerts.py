"""Alert policy, SMS senders (with gateway fallback) and Gemini fallback."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

TEST_DB = Path(__file__).resolve().parent / "_test_farmshield.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["WEATHER_PROVIDER"] = "mock"
os.environ["DEFAULT_SCENARIO"] = "normal"
os.environ["SMS_SENDER"] = "console"
os.environ["GEMINI_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import alerts as svc  # noqa: E402
from app.services import gemini, sms  # noqa: E402


@pytest.fixture(scope="module")
def client():
    engine.dispose()
    if TEST_DB.exists():
        TEST_DB.unlink()
    with TestClient(app) as c:
        c.put("/scenario", json={"scenario": "normal", "reassess": True})
        yield c
    engine.dispose()
    try:
        TEST_DB.unlink()
    except OSError:
        pass


# ------------------------------------------------------------ alert policy ----
def test_low_risk_is_not_alerted(client):
    r = client.post("/farms/3/alerts/preview")  # kale just planted, normal -> LOW
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["level"] == "LOW" and d["would_send"] is False
    assert d["reason"].startswith("below_alert_threshold")
    assert d["chars"] <= 160 and d["message"].startswith("FarmShield")


def test_first_alert_sends_then_dedupes(client):
    client.post("/farms/1/assess")  # maize/flowering under normal -> above LOW
    p = client.post("/farms/1/alerts/preview", json={}).json()
    assert p["would_send"] is True and p["reason"] == "first_alert"
    assert p["language"] == "sw" and p["recipient"] == "+254711000001"

    r = client.post("/farms/1/alerts/send")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["sent"] is True and d["reason"] == "first_alert"
    a = d["alert"]
    assert a["status"] == "sent" and a["provider"] == "console" and a["source"] == "console"
    assert a["language"] == "sw" and a["chars"] <= 160

    again = client.post("/farms/1/alerts/send").json()
    assert again["sent"] is False and again["reason"].startswith("duplicate_within_window")
    assert again["alert"] is None


def test_level_change_beats_dedupe(client):
    before = client.get("/farms/1/risk").json()["overall"]["level"]
    dry = client.post("/farms/1/assess?scenario=dry_spell").json()
    assert dry["overall"]["level"] == "HIGH" and before != "HIGH"
    r = client.post("/farms/1/alerts/send", json={"language": "en"}).json()
    assert r["sent"] is True
    assert r["reason"] == f"level_changed:{before}->HIGH"
    assert r["alert"]["language"] == "en" and "HIGH" in r["alert"]["message"]


def test_force_and_custom_message(client):
    r = client.post("/farms/1/alerts/send", json={"force": True, "message": "  Test   message " + "x" * 200}).json()
    assert r["sent"] is True and r["reason"] == "forced"
    assert len(r["alert"]["message"]) <= 160


def test_alert_history_newest_first(client):
    hist = client.get("/farms/1/alerts").json()
    assert len(hist) == 3
    assert [h["trigger_reason"] for h in hist][0] == "forced"
    assert hist[0]["id"] > hist[1]["id"] > hist[2]["id"]
    assert client.get("/farms/999/alerts").status_code == 404


def test_repeat_allowed_after_window(client):
    settings = get_settings()
    with SessionLocal() as db:
        farm = db.get(models.Farm, 1)
        latest = svc.last_sent_alert(db, 1).assessment
        soon = datetime.now(timezone.utc) + timedelta(hours=1)
        later = datetime.now(timezone.utc) + timedelta(hours=settings.alert_dedupe_hours + 1)
        assert svc.decide(db, farm, latest, now=soon).should_send is False
        d = svc.decide(db, farm, latest, now=later)
        assert d.should_send is True and d.reason == "repeat_after_window"


def test_scenario_switch_with_notify(client):
    r = client.put("/scenario", json={"scenario": "heavy_rain", "reassess": True, "notify": True})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["scenario"] == "heavy_rain" and len(d["reassessed"]) >= 3
    assert isinstance(d["alerts_sent"], list)
    client.put("/scenario", json={"scenario": "normal", "reassess": True})


# ------------------------------------------------------------- sms senders ----
class _FakeAT:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc, self.calls = resp, exc, []

    def send(self, message, recipients, **kw):
        self.calls.append((message, recipients, kw))
        if self.exc:
            raise self.exc
        return self.resp


def test_africastalking_success_parsing():
    s = sms.AfricasTalkingSandboxSender("sandbox", "key", sender_id="FARMSHIELD")
    s._sms = _FakeAT({"SMSMessageData": {"Message": "Sent to 1/1", "Recipients": [{"status": "Success", "statusCode": 101, "messageId": "ATXid_1", "number": "+254711000001"}]}})
    res = s.send("+254711000001", "hello")
    assert res.ok and res.status == "sent" and res.message_id == "ATXid_1" and res.provider == "africastalking"
    assert s._sms.calls[0][2] == {"sender_id": "FARMSHIELD"}


def test_africastalking_down_falls_back_to_console(capsys):
    s = sms.AfricasTalkingSandboxSender("sandbox", "key")
    s._sms = _FakeAT(exc=ConnectionError("gateway timeout"))
    res = sms.send_sms("+254711000001", "hello", sender=s)
    assert res.ok and res.fallback is True and res.provider == "console"
    assert "gateway timeout" in (res.error or "")
    assert "hello" in capsys.readouterr().out


def test_missing_at_key_is_a_clean_failure():
    res = sms.AfricasTalkingSandboxSender("sandbox", "").send("+254700000000", "x")
    assert res.ok is False and "AT_API_KEY" in res.error


def test_send_alert_with_gateway_down_returns_200_and_fallback(client, monkeypatch):
    broken = sms.AfricasTalkingSandboxSender("sandbox", "key")
    broken._sms = _FakeAT(exc=RuntimeError("AT down"))
    monkeypatch.setattr(sms, "get_sms_sender", lambda: broken)
    r = client.post("/farms/2/alerts/send", json={"force": True})
    assert r.status_code == 200, r.text
    a = r.json()["alert"]
    assert r.json()["sent"] is True
    assert a["status"] == "sent" and a["provider"] == "console" and a["source"] == "fallback"
    assert "AT down" in a["error"]


# ------------------------------------------------------------------ gemini ----
def test_gemini_disabled_without_key(client):
    d = client.post("/farms/1/assess").json()
    assert d["advice"]["source"] == "fallback"
    assert d["advice"]["sw"] and d["advice"]["en"]


def test_gemini_failure_falls_back(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-test")
    monkeypatch.setattr(settings, "gemini_model", "gemini-flash-latest")
    # SDK missing or network down -> gemini_advice returns None -> fallback text, HTTP 200
    d = client.post("/farms/1/assess").json()
    assert d["advice"]["source"] == "fallback"


def test_gemini_helpers():
    assert gemini._resolve_model("gemini-flash-latest") == gemini.DEFAULT_MODEL
    assert gemini._resolve_model("") == gemini.DEFAULT_MODEL
    assert gemini._resolve_model("gemini-3.1-flash-lite") == "gemini-3.1-flash-lite"
    fenced = '```json\n{"en": "a", "sw": "b"}\n```'
    assert gemini._extract_json(fenced) == {"en": "a", "sw": "b"}
    assert gemini._extract_json('noise {"en": "x", "sw": "y"} tail') == {"en": "x", "sw": "y"}
    assert gemini._extract_json("not json") is None
