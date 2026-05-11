.PHONY: format lint test run-platform export-openapi contract-sync remote-smoke remote-sync remote-rollback

OPENAPI_SPEC ?= contracts/openapi.json
PYTHON ?= python3
CONDA_ENV ?= duckpark-carla-web

format:
	black app tests
	isort app tests

lint:
	ruff check app tests

test:
	pytest -q

run-platform:
	bash scripts/start_platform.sh

export-openapi:
	@if $(PYTHON) -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then \
		$(PYTHON) scripts/export_openapi.py --output $(OPENAPI_SPEC); \
	elif command -v conda >/dev/null 2>&1; then \
		conda run -n $(CONDA_ENV) python scripts/export_openapi.py --output $(OPENAPI_SPEC); \
	else \
		echo "Python 3.10+ is required. Activate a 3.10 environment or set PYTHON=..."; \
		exit 1; \
	fi

contract-sync: export-openapi
	cd frontend && npm run generate:api-types

remote-smoke:
	python3 scripts/remote_smoke.py --base-url $${REMOTE_API_BASE_URL:-http://$${REMOTE_HOST:-192.168.110.151}:8000} --mode $${SMOKE_MODE:-basic}

remote-sync:
	bash scripts/remote_git_sync.sh deploy

remote-rollback:
	bash scripts/remote_git_sync.sh rollback
