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

## Update Sept 2026 - real Conduit@Empathy API + station data

`POST https://conduit.jhubafrica.com/data.php` (form: `apikey`, `email`, `fromdate`, `todate`) -> JSON, field names expected to match the CSV export.

- [x] `CONDUIT_API_URL`, `CONDUIT_API_KEY`, `CONDUIT_EMAIL` in `config.py` + `.env.example`; never hard-coded or logged
- [x] `providers/weather/conduit_api.py` - `ConduitApiClient.fetch_raw(fromdate, todate)`: httpx form POST, 30 s timeout, 3x backoff on 5xx / timeouts, typed `ConduitError` on non-200 / non-JSON / error envelope, first 300 chars of the body logged
- [x] `scripts/conduit_probe.py` - 1-day discovery call: HTTP status, top-level JSON type / keys, row count, first 2 rows, column names (`make probe`)
- [ ] **run the probe with the real key and finalise the JSON -> Reading mapping** (mapper currently targets the CSV column names, tolerant of missing keys)
- [x] API rows normalised to the same raw-row shape as the GeoCSV parser -> shared `ingest/resample.py` pipeline
- [x] cache `backend/data/cache/conduit_{from}_{to}.json` - 15 min TTL for windows including today, forever for past windows
- [x] ranges chunked into <= 7-day requests, merged, de-duplicated on `Time`
- [x] `WEATHER_PROVIDER=conduit_api | conduit_csv | scenario`, default `conduit_csv`; API failure / missing key -> `conduit_csv` with `data_sources: ["conduit_csv (fallback)"]`; missing CSV -> synthetic scenario, labelled; never 500
- [x] `scripts/conduit_backfill.py --from --to` - pulls history in chunks into the cache and rebuilds `data/conduit_daily.csv` (`make backfill FROM=2026-06-01`)
- [ ] run the backfill once the key arrives and commit `backend/data/conduit_daily.csv`; drop the GeoCSV export at `backend/data/conduit_raw.csv`
- [x] `ingest/geocsv.py` (skip `#` metadata, ISO timestamps, blanks -> None, drop `Health != 0`, de-dupe on `Time`) and `ingest/resample.py` (1-min -> hourly + daily: rain sum, T min/max/mean, RH mean, wind mean / gust max, HI max, WBGT max, light index)
- [x] `ConduitCsvProvider` with replay: virtual clock (`services/clock.py`), `POST /admin/replay/{start|step|reset}` re-assessing every farm
- [x] every assessment / weather / trigger response includes `data_sources: [...]` and `data_coverage: {real_days, synthetic_days, from, to, station: "JKUAT Conduit@Empathy1 (sensor 61)"}`
- [x] tests: `test_ingest.py`, `test_conduit_csv.py`, `test_conduit_api.py` (mocked transport: retry, 4xx, non-JSON, cache TTL, chunking, fallback labels)
- [x] `docs/openapi.json` refrozen; legacy GET-shaped `conduit.py` removed
