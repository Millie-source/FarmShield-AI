## Goal

A pure-Python, dependency-light package `backend/app/engine/` that turns weather history + crop + planting date into an **explainable** risk score and an insurance trigger decision. No FastAPI, no DB, no network: plain data in, plain data out, so it is unit-testable and reusable anywhere. Judges and insurers must be able to see *why* a score is 72, not trust a black box.

## Scope

**In**
- Crop calendars and agronomic thresholds as data (maize, beans, potatoes, tomatoes, kale/sukuma wiki)
- Growth-stage derivation from planting date
- Four sub-scores (drought, flood, heat stress, crop health) + weighted overall score, each with human-readable reasons
- Parametric insurance trigger rules (drought deficit, excess rain)
- Sample 30-day readings for Juja with three scenarios (`normal`, `dry_spell`, `heavy_rain`)
- Validation script/notebook plotting scores over time per scenario
- pytest suite

**Out**
- Persistence, HTTP, Gemini text, SMS (Issue #2)
- UI (Issue #3)
- Real NDVI ingestion (stretch; engine only accepts an optional `ndvi: float | None`)

## Deliverables

- [x] `engine/types.py` - dataclasses `Reading`, `Stage`, `SubScore`, `RiskAssessment`, `TriggerResult`, `Policy`
- [x] `engine/crops.py` - per crop: stages, durations (days), per-stage water need (mm/week), max temp threshold, stage sensitivity weights, wilting soil-moisture threshold. Sources cited in comments (FAO Irrigation & Drainage Paper 56 crop coefficients, KALRO maize and bean guides)
- [x] `engine/stages.py` - `derive_stage(crop, planting_date, today) -> Stage`
- [x] `engine/scoring.py` - `assess(readings, crop, stage, ndvi=None) -> RiskAssessment`
  - drought: rolling 7/30-day rainfall deficit vs stage water need, soil moisture below wilting threshold, consecutive dry days; weighted higher at flowering / grain-fill
  - flood: 24h and 72h totals vs thresholds, soil saturation, rising-rain trend
  - heat: days above crop max temp (esp. flowering), humidity modifier
  - crop health: NDVI if given, else stage progression + cumulative stress; GOOD / FAIR / POOR
  - overall: stage-dependent weighted combination, 0-100 + label
- [x] `engine/insurance.py` - `check_trigger(readings, crop, stage, policy) -> TriggerResult`; drought (cumulative rainfall below threshold over window) and excess-rain triggers
- [x] `backend/app/data/sample_readings.json` - 30 days of realistic Juja readings x 3 scenarios
- [x] `notebooks/engine_validation.py` (or `.ipynb`) - runs the engine over the 3 scenarios and plots scores over time (pitch slide)
- [x] `backend/tests/test_engine_*.py` - stage derivation, each sub-score, overall weighting, both triggers

## Contract

**Exposes** to Issue #2: `engine/types.py` dataclasses and the three functions `derive_stage`, `assess`, `check_trigger`. Every `SubScore` is `{score: 0-100, level: LOW|MEDIUM|HIGH, reasons: list[str]}`; overall is `{score, label}`.

**Consumes**: nothing. `engine/` must never import from outside `engine/` (stdlib only).

## Acceptance criteria

- [x] maize at flowering + `dry_spell` scores **HIGH** overall with a rainfall-deficit reason string
- [x] kale just planted + `normal` scores **LOW**
- [x] beans at vegetative + `normal` lands in **MEDIUM**, distinct from the other two
- [x] every sub-score returns at least one reason
- [x] drought trigger fires for maize/flowering/dry_spell with `window_days=21, rainfall_threshold_mm=30`; does not fire under `normal`
- [x] excess-rain trigger fires under `heavy_rain`
- [x] `pytest backend/tests` green; `engine/` has zero third-party imports

## Suggested order

1. `types.py` + `crops.py` (write the thresholds table first, cite sources)
2. `stages.py` + tests
3. `sample_readings.json` (3 scenarios) + a fixture loader in `tests/conftest.py`
4. `scoring.py` sub-scores one at a time, test-first: drought, heat, flood, crop health, overall
5. `insurance.py` + two trigger tests
6. `notebooks/engine_validation.py` plot
7. PR `feat/engine` into `main`

## Update Sept 2026 - real station has no soil moisture and no W/m² solar

The JKUAT Conduit@Empathy1 station exposes rain gauges, SHT temperature / humidity, wind, Heat Index, Wet Bulb (Globe) Temperature and SI1145 visible / infrared. Engine changes:

- [x] `engine/water_balance.py` - Hargreaves ET₀ (Tmin, Tmax, Tmean, lat -1.0997, day-of-year), ETc = ET₀ x Kc(stage), soil bucket (FC / WP / SAT per soil type, default Juja red clay-loam, 600 mm) -> modelled `soil_moisture_pct`
- [x] drought and flood read the bucket; every reason string says "modelled soil moisture" (or "measured" when a probe value is present)
- [x] heat stress reads station **WBGT** and **Heat Index** maxima with per-crop thresholds in `crops.py`; Tmax kept as fallback; a day is hot when any metric exceeds its limit
- [x] solar -> optional 0-1 `light_index` from SI1145 visible + infrared (relative to the file max); nudges ET₀ by <= 10 %; engine works without it
- [x] `Reading` updated (optional soil, `temp_mean_c`, `wind_gust_ms`, `heat_index_max_c`, `wbgt_max_c`, `light_index`, `synthetic`), `RiskAssessment` exposes `soil_moisture_pct`, `soil_moisture_source`, `et0_mm_day`, `heat_metric`
- [x] tests: `test_water_balance.py` (dry week drains the bucket, a 40 mm day fills it, runoff, probe reset), heat-metric tests; whole suite green
- [x] synthetic scenarios regenerated with station-style columns and labelled synthetic (kept for the live "flip the weather" demo only)
- [ ] calibrate the provisional WBGT / Heat Index thresholds against a season of station data
- [ ] add the ET₀ wind / humidity term (FAO-56 Penman-Monteith) once station wind is trusted
- [ ] re-validate `notebooks/engine_validation.py` on 60-90 real days when the backfill lands
