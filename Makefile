.PHONY: dev api web check lint types test secrets costs probe web-check

PY := uv run

dev:  ## backend on :8000 and the Vite dev server on :5173
	@if [ -f frontend/package.json ]; then \
	  (trap 'kill 0' INT TERM; $(PY) uvicorn demobot.api:app --reload --port 8000 --app-dir backend & \
	   cd frontend && npm run dev -- --host; wait); \
	else $(PY) uvicorn demobot.api:app --reload --port 8000 --app-dir backend; fi

api:
	$(PY) uvicorn demobot.api:app --port 8000 --app-dir backend

check: lint types test secrets web-check  ## everything CI would run; offline

lint:
	$(PY) ruff check backend scripts synth eval
	$(PY) ruff format --check backend scripts synth eval

types:
	$(PY) mypy

test:
	DEMOBOT_FIXTURES=1 $(PY) pytest -m "not live" -q

secrets:
	$(PY) python scripts/secret_scan.py

web-check:
	@if [ -f frontend/package.json ]; then cd frontend && npm run -s typecheck && npm run -s test; else echo "no frontend yet"; fi

costs:  ## the ledger: spend per provider and model, caps left
	$(PY) demobot costs

probe:  ## live: answers the docs/03 PROBE checklist (cached; a re-run costs $0)
	$(PY) python scripts/probe_models.py
