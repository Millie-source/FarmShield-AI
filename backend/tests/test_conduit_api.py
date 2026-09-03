"""Conduit@Empathy API client (retry, cache, chunking, typed errors) and provider fallback - all with a mocked transport."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import httpx
import pytest

from app.providers.weather import ConduitCsvProvider, coverage
from app.providers.weather.conduit_api import ConduitApiClient, ConduitApiProvider, ConduitError, rows_to_readings
from tests.test_conduit_csv import _daily_csv

TODAY = date(2026, 9, 3)


def api_rows(fromdate: date, todate: date, step_min: int = 10) -> list[dict]:
    rows = []
    d = fromdate
    while d <= todate:
        for i in range(0, 24 * 60, step_min):
            t = datetime(d.year, d.month, d.day) + timedelta(minutes=i)
            hot = d.day % 2 == 0
            rows.append({
                "Time": t.strftime("%Y-%m-%d %H:%M:%S"), "Health": 0, "Battery Voltage": 4.0,
                "Rain Gauge 1": 0.3 if (not hot and 12 <= t.hour < 15) else 0.0, "Rain Gauge 2": None,
                "SHT Temperature": (34 if hot else 25) - abs(t.hour - 14) / 4, "SHT Humidity": 30 if hot else 80,
                "Wind Speed": 3.0, "Heat Index": (33 if hot else 27), "Wet Bulb Temperature": 20, "Wet Bulb Globe Temperature": (29.5 if hot else 23),
                "SI1145 Visible": 600, "SI1145 Infrared": 200,
            })
        d += timedelta(days=1)
    return rows


class Fake:
    """Scripted transport: statuses is a list consumed per request, then 200 with data for the window."""

    def __init__(self, statuses=None, body=None, envelope="list"):
        self.statuses = list(statuses or [])
        self.body = body
        self.envelope = envelope
        self.calls: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        form = dict(httpx.QueryParams(request.content.decode()))
        self.calls.append(form)
        assert request.method == "POST" and form["apikey"] and form["email"]
        assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
        if self.statuses:
            st = self.statuses.pop(0)
            return httpx.Response(st, text=f"<html>error {st} for user</html>")
        if self.body is not None:
            return httpx.Response(200, text=self.body)
        rows = api_rows(date.fromisoformat(form["fromdate"]), date.fromisoformat(form["todate"]))
        payload = rows if self.envelope == "list" else {"status": "success", "count": len(rows), "data": rows}
        return httpx.Response(200, json=payload)

    @property
    def transport(self):
        return httpx.MockTransport(self.handler)


def client(fake: Fake, tmp_path=None, **kw) -> ConduitApiClient:
    return ConduitApiClient("k", "e@x.org", "https://conduit.test/data.php", transport=fake.transport, backoff_s=0, cache_dir=tmp_path, **kw)


def test_fetch_raw_posts_form_and_extracts_rows():
    fake = Fake(envelope="dict")
    rows = client(fake).fetch_raw(TODAY - timedelta(days=1), TODAY)
    assert fake.calls[0]["fromdate"] == "2026-09-02" and fake.calls[0]["todate"] == "2026-09-03"
    assert len(rows) == 2 * 144 and "Wet Bulb Globe Temperature" in rows[0]


def test_retries_on_5xx_then_succeeds():
    fake = Fake(statuses=[500, 503])
    c = client(fake)
    rows = c.fetch_raw(TODAY, TODAY)
    assert len(rows) == 144 and c.requests_made == 3


def test_gives_up_after_three_5xx():
    fake = Fake(statuses=[500, 500, 500, 500])
    with pytest.raises(ConduitError) as ei:
        client(fake).fetch_raw(TODAY, TODAY)
    assert "3 attempts" in str(ei.value) and len(fake.calls) == 3


def test_4xx_is_typed_error_without_retry():
    fake = Fake(statuses=[401])
    with pytest.raises(ConduitError) as ei:
        client(fake).fetch_raw(TODAY, TODAY)
    assert ei.value.status == 401 and "error 401" in ei.value.body_snippet and len(fake.calls) == 1


def test_non_json_and_error_envelope_raise():
    with pytest.raises(ConduitError) as ei:
        client(Fake(body="<html>login page</html>")).fetch_raw(TODAY, TODAY)
    assert "non-JSON" in str(ei.value)
    with pytest.raises(ConduitError) as ei:
        client(Fake(body=json.dumps({"status": "error", "message": "Invalid API key"}))).fetch_raw(TODAY, TODAY)
    assert "Invalid API key" in str(ei.value)


def test_timeout_is_retried():
    n = {"i": 0}

    def handler(request):
        n["i"] += 1
        if n["i"] < 3:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, json=api_rows(TODAY, TODAY))

    c = ConduitApiClient("k", "e", "https://conduit.test/data.php", transport=httpx.MockTransport(handler), backoff_s=0)
    assert len(c.fetch_raw(TODAY, TODAY)) == 144 and n["i"] == 3


def test_cache_past_window_forever_and_today_with_ttl(tmp_path):
    fake = Fake()
    c = client(fake, tmp_path)
    past = date(2026, 6, 1)
    c.fetch_raw(past, past + timedelta(days=6))
    c.fetch_raw(past, past + timedelta(days=6))
    assert len(fake.calls) == 1 and (tmp_path / "conduit_2026-06-01_2026-06-07.json").exists()
    today = date.today()
    c.fetch_raw(today, today)
    c.fetch_raw(today, today)
    assert len(fake.calls) == 2  # within TTL -> cached
    c.cache_ttl = timedelta(minutes=0)
    c.fetch_raw(today, today)
    assert len(fake.calls) == 3  # TTL expired -> refetched


def test_fetch_range_chunks_into_7_days_and_dedupes(tmp_path):
    fake = Fake()
    c = client(fake, tmp_path)
    rows = c.fetch_range(TODAY - timedelta(days=19), TODAY)
    assert [(f["fromdate"], f["todate"]) for f in fake.calls] == [
        ("2026-08-15", "2026-08-21"), ("2026-08-22", "2026-08-28"), ("2026-08-29", "2026-09-03"),
    ]
    assert len(rows) == 20 * 144
    times = [r["Time"] for r in rows]
    assert len(times) == len(set(times))


def test_extract_rows_handles_envelopes():
    ex = ConduitApiClient.extract_rows
    assert ex([{"a": 1}]) == [{"a": 1}]
    assert ex({"data": [{"a": 1}]}) == [{"a": 1}]
    assert ex({"result": {"rows": [{"a": 1}]}}) == [{"a": 1}]
    assert ex({"whatever": [{"a": 1}], "count": 1}) == [{"a": 1}]
    assert ex({"2026-09-01 00:00:00": {"SHT Temperature": 20}}) == [{"Time": "2026-09-01 00:00:00", "SHT Temperature": 20}]
    assert ex({"status": "ok"}) == []


def test_rows_to_readings_go_through_the_shared_pipeline():
    readings = rows_to_readings(api_rows(TODAY - timedelta(days=2), TODAY))
    assert len(readings) == 3 and not any(r.synthetic for r in readings)
    hot = [r for r in readings if r.date.day % 2 == 0][0]
    assert hot.wbgt_max_c == 29.5 and hot.heat_index_max_c == 33 and hot.rainfall_mm == 0.0 and hot.soil_moisture_pct is None
    wet = [r for r in readings if r.date.day % 2 == 1][0]
    assert wet.rainfall_mm == pytest.approx(0.3 * 18, abs=0.2)


# ------------------------------------------------------------------ provider ----
def test_provider_uses_api_and_pads(tmp_path):
    p = ConduitApiProvider(client(Fake(), tmp_path), fallback=ConduitCsvProvider(tmp_path / "none.csv"))
    hist = p.get_history(-1.1, 37.0, days=30, end=TODAY)
    assert coverage(hist)["real_days"] == 30 and p.source_id() == "conduit_api"
    assert p.data_sources(hist) == ["conduit_api"] and p.scenario is None
    short = p.get_history(-1.1, 37.0, days=3, end=TODAY)
    assert len(short) == 3 and not any(r.synthetic for r in short)


def test_provider_falls_back_to_csv_when_api_down(tmp_path):
    csv_p = ConduitCsvProvider(_daily_csv(tmp_path, days=5))
    p = ConduitApiProvider(client(Fake(statuses=[500, 500, 500]), tmp_path / "cache"), fallback=csv_p)
    hist = p.get_history(-1.1, 37.0, days=30, end=TODAY)
    assert p.source_id() == "conduit_csv (fallback)"
    assert p.data_sources(hist) == ["conduit_csv (fallback)", "synthetic:normal (backfill)"]
    assert coverage(hist) == {**coverage(hist), "real_days": 5, "synthetic_days": 25}


def test_provider_without_credentials_falls_back(tmp_path):
    p = ConduitApiProvider(None, fallback=ConduitCsvProvider(tmp_path / "none.csv"))
    hist = p.get_history(-1.1, 37.0, days=30, end=TODAY)
    assert all(r.synthetic for r in hist)
    assert p.source_id().endswith("(conduit_csv missing) (fallback)") and p.scenario == "normal"


def test_client_requires_credentials():
    with pytest.raises(ValueError):
        ConduitApiClient("", "")
