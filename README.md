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

## Integration checklist

- [ ] `feat/engine` merged: `backend/app/engine` green under pytest
- [ ] `feat/backend` merged: curl walkthrough passes against mock provider
- [ ] `feat/frontend` merged: demo path clickable in under 2 minutes
- [ ] `docs/openapi.json` frozen and frontend client matches
- [ ] Conduit station adapter wired to the live endpoint
- [ ] `.env` keys set (Gemini, Africa's Talking sandbox)

_Sections to come: architecture diagram, scoring methodology, API walkthrough, how to demo._
