## Goal

The FastAPI service that ingests weather data, persists farms and assessments, wraps the engine from Issue #1, exposes the farmer API and the partner (insurer / bank / SACCO) API, generates farmer-friendly advice (EN + SW) and sends SMS alerts. Must run locally with `make dev`, degrade gracefully when Gemini / Africa's Talking / Conduit are down, and never return a 500 for an external failure.

## Scope

**In**
- SQLAlchemy models + SQLite, seed script (3 demo farms near Juja, 2 partner API clients)
- `WeatherProvider` interface with `MockProvider` (scenario replay) and `ConduitProvider` (JKUAT Conduit station); `SatelliteProvider` stub
- Farmer endpoints, partner endpoints with `X-API-Key` auth
- Gemini advisor with rule-based fallback
- SMS sender adapters + alert dedupe logic
- Polished OpenAPI docs, CORS, `.env.example`, frozen `docs/openapi.json`

**Out**
- Scoring logic itself (Issue #1 - imported, not reimplemented)
- UI (Issue #3)
- Auth for farmers (demo only), payments, real policy issuance

## Deliverables

- [x] `models.py` - `Farmer`, `Farm`, `WeatherReading`, `RiskAssessment`, `Alert`, `ApiClient`
- [x] `seed.py` - 3 farms (maize/flowering, beans/vegetative, kale/just planted; lat -1.10, lon 37.01 area) + clients `acme-insurance`, `harvest-sacco`
- [x] `providers/weather/base.py` - `get_latest(lat, lon)`, `get_history(lat, lon, days)`
- [x] `providers/weather/mock.py` - replays `data/sample_readings.json`, `scenario` switch (`normal` / `dry_spell` / `heavy_rain`) settable via `?scenario=` and a global `PUT /scenario`
- [x] `providers/weather/conduit.py` - JKUAT Conduit adapter (payload shape **still TBC** - field aliases in `FIELD_ALIASES`), timeout + fallback to mock on failure
- [x] `providers/satellite/base.py` - stub returning `None` / mock NDVI
- [x] Farmer routes: `POST /farms`, `GET /farms`, `GET /farms/{id}`, `POST /farms/{id}/assess`, `GET /farms/{id}/risk`, `GET /farms/{id}/risk/history`, `GET /farms/{id}/weather?days=30`
- [x] Partner routes under `/api/v1` with `X-API-Key`: `GET /risk/{farm_id}`, `GET /risk/bulk?farm_ids=`, `POST /insurance/check-trigger`
- [x] `engine/advisor.py` - Gemini `gemini-3.1-flash-lite` (never `gemini-flash-latest`) -> advice EN + SW from the structured assessment; rule-based fallback text when key missing / call fails
- [x] `services/sms.py` - `SmsSender` interface, `AfricasTalkingSandboxSender`, `ConsoleSender`; messages under 160 chars where possible
- [x] `services/alerts.py` - decides when a score change warrants SMS; dedupes (no repeat within N hours unless level changes)
- [x] Alert routes: `POST /farms/{id}/alerts/preview`, `POST /farms/{id}/alerts/send`, `GET /farms/{id}/alerts`
- [x] OpenAPI: description + example on every schema and route; `docs/openapi.json` frozen via `make openapi`
- [x] `.env.example`, CORS for `:5173`, `make dev` / `dev.ps1 dev`
- [x] README curl walkthrough

## Contract

**Exposes** to Issue #3: the OpenAPI spec at `/openapi.json`, frozen to `docs/openapi.json` as soon as schemas stabilise. Key response shape for `GET /farms/{id}/risk` and `GET /api/v1/risk/{farm_id}`:

```json
{
  "farm_id": 1, "crop": "maize", "stage": {"name": "flowering", "day": 62, "progress": 0.55},
  "overall": {"score": 72, "label": "HIGH CLIMATE RISK", "level": "HIGH"},
  "sub_scores": {
    "drought": {"score": 81, "level": "HIGH", "reasons": ["Only 4 mm rain in last 7 days vs 25 mm needed at flowering"]},
    "flood": {}, "heat": {}, "crop_health": {}
  },
  "insurance_trigger": {"triggered": true, "rule": "drought_deficit", "evidence": {}, "confidence": 0.86},
  "advice": {"en": "...", "sw": "...", "source": "gemini"},
  "assessed_at": "2026-09-03T10:00:00Z",
  "data_sources": ["mock:dry_spell"]
}
```

**Consumes** from Issue #1: `engine/types.py`, `derive_stage`, `assess`, `check_trigger`.

## Acceptance criteria

- [x] README curl walkthrough works end-to-end against the mock provider
- [x] switching scenario (`?scenario=dry_spell` or `PUT /scenario`) changes scores on re-assess
- [x] partner key gives 200; missing or invalid key gives 401 with a clear JSON error
- [x] Gemini or Africa's Talking down: advice falls back / SMS logs to console, HTTP still 200 with `source: "fallback"`
- [x] `/docs` reads well: every schema has descriptions and examples
- [x] `docs/openapi.json` committed

## Suggested order

1. `models.py`, DB session, `seed.py`, `POST/GET /farms` - verify with curl
2. `providers/weather/{base,mock}.py` + `GET /farms/{id}/weather`
3. `POST /farms/{id}/assess` wiring the engine; `GET /risk`, `/risk/history`
4. Partner router + `X-API-Key` dependency + seeded clients; polish schemas; freeze `docs/openapi.json`
5. `advisor.py` with fallback; `sms.py` + `alerts.py` + alert routes
6. `conduit.py` once the payload is known; `PUT /scenario`
7. PR `feat/backend` into `main`
