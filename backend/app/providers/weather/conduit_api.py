"""ConduitApiProvider: live data from the Conduit@Empathy API (JHUB Africa).

    POST https://conduit.jhubafrica.com/data.php
    Content-Type: application/x-www-form-urlencoded
    apikey=...&email=...&fromdate=YYYY-MM-DD&todate=YYYY-MM-DD   -> JSON

The exact JSON shape is confirmed with ``scripts/conduit_probe.py``; until then rows are mapped by the
CSV export column names through ``ingest/geocsv.normalise_rows`` (tolerant of missing keys) and fed through
the same ``ingest/resample`` pipeline as the file provider, so the engine sees one format regardless of source.

Resilience: 30 s timeout, 3 attempts with backoff on 5xx / timeouts, typed ``ConduitError`` on non-200 or
non-JSON (first 300 chars of the body logged so auth errors are visible), <=7-day chunks merged and
de-duplicated on Time, per-window JSON cache (15 min TTL for windows that include today, forever for past
windows).  Any failure falls back to the CSV provider and labels ``data_sources`` "... (fallback)".
The API key and e-mail are never logged.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from app.engine.types import Reading
from app.ingest import geocsv, resample

from .base import WeatherProvider
from .conduit_csv import ConduitCsvProvider, pad_history
from .scenario import ScenarioWeatherProvider

log = logging.getLogger("farmshield.conduit_api")

DEFAULT_URL = "https://conduit.jhubafrica.com/data.php"
BODY_SNIPPET = 300
LIST_KEYS = ("data", "rows", "records", "result", "results", "readings", "items", "payload")


class ConduitError(RuntimeError):
    """Non-200, non-JSON or empty response from the Conduit API."""

    def __init__(self, message: str, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body_snippet = body[:BODY_SNIPPET]


class ConduitApiClient:
    def __init__(
        self,
        api_key: str,
        email: str,
        url: str = DEFAULT_URL,
        *,
        timeout_s: float = 30.0,
        retries: int = 3,
        backoff_s: float = 1.5,
        cache_dir: Path | None = None,
        cache_ttl_min: int = 15,
        chunk_days: int = 7,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key or not email:
            raise ValueError("Conduit API needs CONDUIT_API_KEY and CONDUIT_EMAIL")
        self._api_key = api_key
        self._email = email
        self.url = url or DEFAULT_URL
        self.timeout_s = timeout_s
        self.retries = max(1, retries)
        self.backoff_s = backoff_s
        self.cache_dir = cache_dir
        self.cache_ttl = timedelta(minutes=cache_ttl_min)
        self.chunk_days = max(1, chunk_days)
        self._transport = transport
        self.requests_made = 0

    # ------------------------------------------------------------------ cache ----
    def _cache_path(self, fromdate: date, todate: date) -> Path | None:
        return self.cache_dir / f"conduit_{fromdate.isoformat()}_{todate.isoformat()}.json" if self.cache_dir else None

    def _cache_get(self, fromdate: date, todate: date) -> list[dict[str, Any]] | None:
        p = self._cache_path(fromdate, todate)
        if not p or not p.exists():
            return None
        if todate >= date.today():  # window includes today -> honour the TTL
            age = datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)
            if age > self.cache_ttl:
                return None
        try:
            rows = json.loads(p.read_text(encoding="utf-8"))
            return rows if isinstance(rows, list) else None
        except (OSError, json.JSONDecodeError):
            return None

    def _cache_put(self, fromdate: date, todate: date, rows: list[dict[str, Any]]) -> None:
        p = self._cache_path(fromdate, todate)
        if not p:
            return
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            log.warning("Could not write Conduit cache %s: %s", p.name, exc)

    # ------------------------------------------------------------------- HTTP ----
    def request_raw(self, fromdate: date, todate: date) -> httpx.Response:
        """One POST with retries. Returns the response (any status) or raises ConduitError on transport failure."""
        form = {"apikey": self._api_key, "email": self._email, "fromdate": fromdate.isoformat(), "todate": todate.isoformat()}
        last_exc: Exception | None = None
        for attempt in range(self.retries):
            try:
                with httpx.Client(timeout=self.timeout_s, transport=self._transport) as client:
                    self.requests_made += 1
                    resp = client.post(self.url, data=form, headers={"Accept": "application/json"})
                if resp.status_code >= 500:
                    last_exc = ConduitError(f"Conduit API HTTP {resp.status_code}", resp.status_code, resp.text)
                    log.warning("Conduit API HTTP %s (attempt %d/%d): %s", resp.status_code, attempt + 1, self.retries, resp.text[:BODY_SNIPPET])
                else:
                    return resp
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                log.warning("Conduit API %s (attempt %d/%d)", type(exc).__name__, attempt + 1, self.retries)
            if attempt < self.retries - 1 and self.backoff_s:
                time.sleep(self.backoff_s * (2**attempt))
        raise ConduitError(f"Conduit API unreachable after {self.retries} attempts: {last_exc}") from last_exc

    @staticmethod
    def extract_rows(payload: Any) -> list[dict[str, Any]]:
        """Find the list of records in whatever envelope the API uses."""
        if isinstance(payload, list):
            return [r for r in payload if isinstance(r, dict)]
        if isinstance(payload, dict):
            for k in LIST_KEYS:
                v = payload.get(k)
                if isinstance(v, list):
                    return [r for r in v if isinstance(r, dict)]
                if isinstance(v, dict):
                    inner = ConduitApiClient.extract_rows(v)
                    if inner:
                        return inner
            for v in payload.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    return v
            if payload and all(isinstance(v, dict) for v in payload.values()):
                return [{"Time": k, **v} for k, v in payload.items()]  # {timestamp: {...}}
        return []

    def fetch_raw(self, fromdate: date, todate: date, use_cache: bool = True) -> list[dict[str, Any]]:
        """Rows for one window (<= chunk_days recommended). Raises ConduitError on non-200 / non-JSON / no rows."""
        if use_cache:
            cached = self._cache_get(fromdate, todate)
            if cached is not None:
                return cached
        resp = self.request_raw(fromdate, todate)
        if resp.status_code != 200:
            log.warning("Conduit API HTTP %s for %s..%s: %s", resp.status_code, fromdate, todate, resp.text[:BODY_SNIPPET])
            raise ConduitError(f"Conduit API HTTP {resp.status_code}", resp.status_code, resp.text)
        try:
            payload = resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            log.warning("Conduit API returned non-JSON for %s..%s: %s", fromdate, todate, resp.text[:BODY_SNIPPET])
            raise ConduitError("Conduit API returned non-JSON", resp.status_code, resp.text) from exc
        if isinstance(payload, dict) and str(payload.get("status", payload.get("success", ""))).lower() in ("error", "false", "fail", "failed"):
            msg = str(payload.get("message") or payload.get("error") or payload)[:BODY_SNIPPET]
            log.warning("Conduit API error payload for %s..%s: %s", fromdate, todate, msg)
            raise ConduitError(f"Conduit API error: {msg}", resp.status_code, resp.text)
        rows = self.extract_rows(payload)
        if use_cache:
            self._cache_put(fromdate, todate, rows)
        return rows

    def fetch_range(self, fromdate: date, todate: date, use_cache: bool = True) -> list[dict[str, Any]]:
        """Long ranges in <= chunk_days windows, merged and de-duplicated on Time."""
        if todate < fromdate:
            fromdate, todate = todate, fromdate
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        cur = fromdate
        while cur <= todate:
            end = min(todate, cur + timedelta(days=self.chunk_days - 1))
            for row in self.fetch_raw(cur, end, use_cache=use_cache):
                key = _time_key(row)
                if key is None or key in seen:
                    continue
                seen.add(key)
                out.append(row)
            cur = end + timedelta(days=1)
        return out


def _time_key(row: dict[str, Any]) -> str | None:
    for k, v in row.items():
        if geocsv.normalise_key(k) in geocsv.COLUMN_ALIASES["time"]:
            return str(v)
    return None


def rows_to_readings(rows: list[dict[str, Any]], min_records: int = 12) -> list[Reading]:
    """API JSON rows -> normalised raw records -> daily aggregates -> Readings (real, not synthetic)."""
    if not rows:
        return []
    return resample.to_readings(resample.daily(geocsv.normalise_rows(rows), min_records=min_records))


class ConduitApiProvider(WeatherProvider):
    name = "conduit_api"

    def __init__(self, client: ConduitApiClient | None, fallback: WeatherProvider | None = None, pad_scenario: str = "normal") -> None:
        self.client = client
        self.fallback = fallback or ConduitCsvProvider("data/conduit_daily.csv")
        self.pad = ScenarioWeatherProvider(pad_scenario)
        self._ok = False
        self._warned_no_creds = False

    @classmethod
    def from_settings(cls, s, fallback: WeatherProvider | None = None) -> "ConduitApiProvider":
        from . import backend_path

        client = None
        if s.conduit_api_key and s.conduit_email:
            client = ConduitApiClient(
                s.conduit_api_key,
                s.conduit_email,
                s.conduit_api_url or DEFAULT_URL,
                cache_dir=backend_path(s.conduit_cache_dir),
                cache_ttl_min=s.conduit_cache_ttl_min,
            )
        return cls(client, fallback=fallback)

    def get_history(self, lat: float, lon: float, days: int = 30, end: date | None = None) -> list[Reading]:
        end = end or date.today()
        if self.client is None:
            if not self._warned_no_creds:
                log.warning("WEATHER_PROVIDER=conduit_api but CONDUIT_API_KEY / CONDUIT_EMAIL not set; using %s", self.fallback.name)
                self._warned_no_creds = True
            self._ok = False
            return self.fallback.get_history(lat, lon, days, end)
        try:
            rows = self.client.fetch_range(end - timedelta(days=days - 1), end)
            readings = [r for r in rows_to_readings(rows) if r.date <= end]
            if not readings:
                raise ConduitError("Conduit API returned no scoreable daily readings")
            self._ok = True
            return pad_history(readings[-days:], days, end, self.pad)
        except Exception as exc:  # noqa: BLE001 - never 500 because the station API is down
            log.warning("Conduit API unavailable (%s: %s); falling back to %s", type(exc).__name__, str(exc)[:BODY_SNIPPET], self.fallback.name)
            self._ok = False
            return self.fallback.get_history(lat, lon, days, end)

    def source_id(self) -> str:
        return "conduit_api" if self._ok else f"{self.fallback.source_id()} (fallback)"

    @property
    def scenario(self) -> str | None:
        return None if self._ok else self.fallback.scenario
