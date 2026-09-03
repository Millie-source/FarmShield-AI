# FarmShield AI - developer commands
# Windows without GNU make: use ./dev.ps1 (same targets).
PY ?= python
VENV = backend/.venv
ifeq ($(OS),Windows_NT)
  VPY = $(VENV)/Scripts/python
else
  VPY = $(VENV)/bin/python
endif

.PHONY: setup dev api web test seed openapi probe backfill clean

setup: ## install backend + frontend deps
	$(PY) -m venv $(VENV)
	$(VPY) -m pip install -q -e "backend[dev]"
	cd frontend && npm install

api: ## run FastAPI on :8000
	cd backend && ../$(VPY) -m uvicorn app.main:app --reload --port 8000

web: ## run Vite dev server on :5173
	cd frontend && npm run dev

dev: ## run API + frontend together
	$(MAKE) -j2 api web

test: ## backend unit tests
	cd backend && ../$(VPY) -m pytest -q

seed: ## (re)seed demo farms + partner API clients
	cd backend && ../$(VPY) -m app.seed

openapi: ## freeze OpenAPI spec to docs/openapi.json
	cd backend && ../$(VPY) -m app.export_openapi

probe: ## call the Conduit API for 1 day and print its shape (needs CONDUIT_API_KEY + CONDUIT_EMAIL in backend/.env)
	cd backend && ../$(VPY) scripts/conduit_probe.py

FROM ?= 2026-06-01
TO ?= $(shell date +%Y-%m-%d)
backfill: ## pull Conduit history in 7-day chunks into the cache and rebuild data/conduit_daily.csv
	cd backend && ../$(VPY) scripts/conduit_backfill.py --from $(FROM) --to $(TO)

clean:
	rm -rf $(VENV) backend/farmshield.db frontend/node_modules
