## Goal

The Vite + React + Tailwind app that makes the **Farm Risk Score** the hero of the demo and presents the partner API as a real product. Full demo path clickable in under 2 minutes.

## Scope

**In**
- Dashboard, FarmDetail (hero risk panel), RegisterFarm, PartnerApi pages
- Header scenario switcher (`normal` / `dry_spell` / `heavy_rain`) with animated score changes
- Typed API client from `docs/openapi.json`; loading / error states; mobile-friendly
- Local mock (MSW or static JSON) so UI work never blocks on the backend

**Out**
- Any scoring or advice logic (server-side)
- Auth beyond picking a demo API key
- Offline / PWA

## Deliverables

- [x] `pages/Dashboard.tsx` - farm cards: name, crop + stage, overall score, colour-coded level
- [x] `pages/FarmDetail.tsx` - the hero panel:

  ```
  FARM RISK SCORE
  Drought Risk      🔴 HIGH
  Flood Risk        🟡 MEDIUM
  Heat Stress       🔴 HIGH
  Crop Health       🟢 GOOD
  Overall  72 / 100  — HIGH CLIMATE RISK
  ```
  plus: "why" reasons list, advice card with EN / SW toggle, 30-day rainfall + temperature chart (Recharts), alert history, **Send SMS alert** button with exact message preview
- [x] `pages/RegisterFarm.tsx` - name, phone, crop, planting date, location (lat/lon inputs or Leaflet map click)
- [x] `pages/PartnerApi.tsx` - "For insurers & banks": pick demo API key (`acme-insurance` / `harvest-sacco`), choose farm, fire request live, show request + JSON response side by side, bulk / portfolio table
- [x] Header scenario switcher: calls backend scenario switch + re-assess, animates score deltas
- [x] `src/api/` typed client generated or hand-written from `docs/openapi.json`
- [x] Loading skeletons, error toasts, responsive layout

## Contract

**Consumes** from Issue #2: `docs/openapi.json`. Until it exists, build against `src/mocks/` fixtures matching the response shape in Issue #2.

Routes used: `GET /farms`, `POST /farms`, `GET /farms/{id}`, `GET /farms/{id}/risk`, `POST /farms/{id}/assess`, `GET /farms/{id}/weather?days=30`, `GET /farms/{id}/alerts`, `POST /farms/{id}/alerts/preview`, `POST /farms/{id}/alerts/send`, `PUT /scenario`, `GET /api/v1/risk/{farm_id}`, `GET /api/v1/risk/bulk`, `POST /api/v1/insurance/check-trigger`.

## Acceptance criteria

- [x] register farm, see score, flip scenario, see score change, SMS preview, partner page, fire API call: all in under 2 minutes
- [x] hero panel matches the layout above with 🔴 🟡 🟢 and `72 / 100 — HIGH CLIMATE RISK`
- [x] EN / SW toggle swaps advice text
- [x] chart shows 30 days of rainfall (bars) + temperature (line)
- [x] partner page shows request headers incl. `X-API-Key` and pretty-printed JSON response; invalid key shows the 401
- [x] usable on a phone-width viewport

## Suggested order

1. Layout shell, router, Tailwind theme, header with scenario switcher (stubbed)
2. API client + mock fixtures
3. Dashboard cards
4. FarmDetail hero panel, reasons, advice toggle, chart, alerts
5. RegisterFarm
6. PartnerApi page
7. Swap mocks for the real backend; polish animations, mobile
8. PR `feat/frontend` into `main`

## Update Sept 2026 - show the real station data provenance

- [x] `data_coverage` badge on FarmDetail: "5 real days · 25 modelled days · JKUAT station" (tooltip: station, date range, sources) - `components/DataCoverageBadge.tsx`
- [x] `data_sources` chips + coverage badge under the JSON in the partner API response viewer
- [x] `api/types.ts` updated: `DataCoverage`, new `WeatherReading` fields (WBGT, heat index, light index, optional soil, `synthetic`), `Risk.soil_moisture_pct/_source`, `heat_metric`
- [x] weather chart footer shows *modelled* soil moisture and the 7-day WBGT peak / which heat metric drove the score
- [ ] header replay controls (`POST /admin/replay/start | step | reset`) so the pitch can walk through the real season
- [ ] chart: WBGT / heat-index line and the modelled soil-moisture series (`GET /farms/{id}/weather` already returns the fields)
- [ ] mark synthetic days visually in the rainfall bars (`readings[].synthetic`)
