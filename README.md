# FarmShield AI

**Hyperlocal climate risk infrastructure for smallholder farmers in Kenya.**
Built for JHUB Africa *Hack the Weather 2026* - theme "From Data to Impact".

Farmers do not need raw forecasts; they need answers: *Should I irrigate today? Is my maize in a drought-risk window? Can this weather event trigger my insurance?*
FarmShield turns weather station readings + crop + growth stage + location into an explainable **Farm Risk Score**, stage-aware advice (English + Kiswahili, via SMS) and parametric **insurance trigger signals**, then exposes all of it through a clean REST API for insurers, banks, SACCOs and agribusinesses.

```
Farmer -> Farm registration -> Weather (JKUAT Conduit) + satellite -> Climate Risk Engine
       -> Dynamic Risk Score -> API -> Insurers / Banks / SACCOs / Agribusinesses
```

## Quick start

```bash
make setup      # venv + pip + npm install
make dev        # API on :8000, dashboard on :5173
```

Windows without GNU make:

```powershell
.\dev.ps1 setup
.\dev.ps1 dev
```

Copy `.env.example` to `.env` and fill in keys (everything degrades gracefully without them).

- API docs: http://localhost:8000/docs
- Dashboard: http://localhost:5173

## Repo layout

```
backend/   FastAPI + SQLAlchemy (SQLite) + rule-based risk engine
frontend/  Vite + React + Tailwind dashboard
docs/      OpenAPI freeze, issue specs, architecture
notebooks/ engine validation over the demo scenarios
```

## Work breakdown

| # | Area | Issue |
|---|------|-------|
| 1 | Data Science - Climate Risk Engine | [#1](https://github.com/Millie-source/FarmShield-AI/issues/1) - branch `feat/engine` |
| 2 | Backend - API, pipeline & integrations | [#2](https://github.com/Millie-source/FarmShield-AI/issues/2) - branch `feat/backend` |
| 3 | Frontend - Farmer dashboard & partner demo | [#3](https://github.com/Millie-source/FarmShield-AI/issues/3) - branch `feat/frontend` |

## API walkthrough (mock provider)

Everything below runs against the bundled Juja readings, no keys needed. Start the API with `make api`
(or `make dev`), then in another shell:

```bash
B=http://localhost:8000
K="X-API-Key: fs_demo_acme_insurance_2026"   # demo partner key (also: fs_demo_harvest_sacco_2026)

# 1. Health + the three seeded demo farms (maize/flowering, beans/vegetative, kale/just planted)
curl -s $B/health
curl -s $B/farms | python3 -m json.tool

# 2. Register a farm (07xx numbers are normalised to +2547xx). Runs a first assessment immediately.
curl -s -X POST $B/farms -H 'Content-Type: application/json' -d '{
  "farmer_name": "Grace Njeri", "phone": "0722000010", "language": "en",
  "farm_name": "Njeri Tomatoes", "crop": "tomatoes", "planting_date": "2026-07-20",
  "lat": -1.105, "lon": 37.015, "area_ha": 0.3 }'

# 3. The Farm Risk Score for the maize plot, then re-assess it under a dry spell (per-call override)
curl -s $B/farms/1/risk | python3 -m json.tool
curl -s -X POST "$B/farms/1/assess?scenario=dry_spell" | python3 -m json.tool
#   -> overall.level HIGH, insurance_trigger.triggered true, advice.en / advice.sw, advice.source "fallback"
#      (becomes "gemini" once GEMINI_API_KEY is set)

# 4. Weather the score was based on, and the assessment history
curl -s "$B/farms/1/weather?days=7"
curl -s "$B/farms/1/risk/history"

# 5. SMS alerts: preview the exact <=160-char message, send it, try again (deduped), list history
curl -s -X POST $B/farms/1/alerts/preview | python3 -m json.tool
curl -s -X POST $B/farms/1/alerts/send      # sent: true,  reason: first_alert (console prints the SMS)
curl -s -X POST $B/farms/1/alerts/send      # sent: false, reason: duplicate_within_window:6h
curl -s -X POST $B/farms/1/alerts/send -H 'Content-Type: application/json' -d '{"force": true, "language": "en"}'
curl -s $B/farms/1/alerts

# 6. Live-demo switch: flip every farm to heavy rain, re-assess, and alert farmers whose level changed
curl -s -X PUT $B/scenario -H 'Content-Type: application/json' -d '{"scenario": "heavy_rain", "reassess": true, "notify": true}'
curl -s -X PUT $B/scenario -H 'Content-Type: application/json' -d '{"scenario": "normal"}'

# 7. Partner API (insurers / banks / SACCOs) - X-API-Key required
curl -s -i $B/api/v1/risk/1 | head -1                 # 401 {"detail": "Missing X-API-Key header"}
curl -s -H "X-API-Key: nope" $B/api/v1/risk/1         # 401 {"detail": "Invalid or inactive API key"}
curl -s -H "$K" $B/api/v1/me
curl -s -H "$K" $B/api/v1/risk/1 | python3 -m json.tool
curl -s -H "$K" "$B/api/v1/risk/bulk?farm_ids=1,2,3"  # portfolio roll-up + per-farm results
curl -s -X POST -H "$K" -H 'Content-Type: application/json' $B/api/v1/insurance/check-trigger -d '{
  "farm_id": 1, "scenario": "dry_spell",
  "policy": {"type": "drought", "window_days": 21, "rainfall_threshold_mm": 30, "critical_stages_only": true} }'
#   -> triggered true, rule drought_rainfall_deficit, evidence.rainfall_total_mm 0.4
```

### Graceful degradation

| Dependency | Missing / down | Response |
|---|---|---|
| Gemini (`GEMINI_API_KEY`) | key unset, SDK missing, timeout, bad JSON | rule-based EN + SW advice, `advice.source: "fallback"`, HTTP 200 |
| Africa's Talking (`SMS_SENDER=africastalking`) | key unset, SDK error, gateway down | SMS printed to console, alert stored with `source: "fallback"`, HTTP 200 |
| JKUAT Conduit (`WEATHER_PROVIDER=conduit`) | URL unset, timeout, unparsable payload | mock readings, `data_sources: ["mock:<scenario> (conduit unavailable)"]` |

Alert policy (`services/alerts.py`): no SMS for LOW risk unless an insurance trigger fired; no repeat within
`ALERT_DEDUPE_HOURS` (default 6) unless the overall level changed or a trigger newly fired; `force: true` always sends.

Run `make openapi` after changing any schema to refreeze `docs/openapi.json` for the frontend client.

## Integration checklist

- [ ] `feat/engine` merged: `backend/app/engine` green under pytest
- [ ] `feat/backend` merged: curl walkthrough passes against mock provider
- [ ] `feat/frontend` merged: demo path clickable in under 2 minutes
- [ ] `docs/openapi.json` frozen and frontend client matches
- [ ] Conduit station adapter wired to the live endpoint
- [ ] `.env` keys set (Gemini, Africa's Talking sandbox)

_Sections to come: architecture diagram, scoring methodology, how to demo._
