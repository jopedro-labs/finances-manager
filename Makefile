.PHONY: help migrate snapshot analysis analysis-refresh dashboard projections quality quality-refresh gdrive-push gdrive-pull report report-html report-md clean lint security

PYTHON := .venv/bin/python3
RUFF   := .venv/bin/ruff
MYPY   := .venv/bin/mypy
BANDIT := .venv/bin/bandit
export PYTHONPATH := $(CURDIR)

help:
	@echo "Portfolio Manager -- Available commands:"
	@echo "  make snapshot         - Extract data from XTB screenshot in input/ and run snapshot"
	@echo "  make analysis         - Run portfolio and asset performance analysis (cached fundamentals)"
	@echo "  make analysis-refresh - Run portfolio analysis forcing live API fetch (bypassing cache)"
	@echo "  make dashboard        - Compute dashboard overview metrics and time-series aggregates"
	@echo "  make projections      - Run compound growth and wealth accumulation simulations"
	@echo "  make quality          - Evaluate fundamental quality tiers for stocks and ETFs (cached)"
	@echo "  make quality-refresh  - Evaluate fundamental quality tiers forcing live API fetch"
	@echo "  make gdrive-push      - Push/upload local database and JSON configs to Google Drive"
	@echo "  make gdrive-pull      - Pull/download database and JSON configs from Google Drive"
	@echo "  make report           - Generate daily report as Markdown saved to reports/"
	@echo "  make report-html      - Generate report as HTML saved to reports/"
	@echo "  make report-md        - Generate report as Markdown saved to reports/ (alias)"
	@echo "  make migrate          - Reconcile portfolio seed JSON into SQLite database\n\t@echo "  make clean            - Remove generated files (reports/, temp snapshot)"
	@echo "  make lint             - Run ruff (lint + format check) and mypy (type check)"
	@echo "  make security         - Run bandit security scan"

snapshot:
	@echo "[make snapshot] Step 1: Pulling latest database from Google Drive..."
	@$(PYTHON) scripts/gdrive_db_sync.py --pull
	@echo "[make snapshot] Step 2: Running automated XTB screenshot extraction, saving snapshot & pushing to GDrive..."
	@$(PYTHON) scripts/run_snapshot.py

quality:
	@echo "[make quality] Step 1: Pulling latest JSON configs from Google Drive..."
	@$(PYTHON) scripts/gdrive_jsons_sync.py --pull
	@echo "[make quality] Step 2: Evaluating stock and ETF fundamental quality tiers..."
	@$(PYTHON) scripts/run_quality.py

quality-refresh:
	@echo "[make quality-refresh] Step 1: Pulling latest JSON configs from Google Drive..."
	@$(PYTHON) scripts/gdrive_jsons_sync.py --pull
	@echo "[make quality-refresh] Step 2: Evaluating fundamental quality tiers with forced live refresh..."
	@$(PYTHON) scripts/run_quality.py --force-refresh

analysis:
	@echo "[make analysis] Step 1: Pulling latest database from Google Drive..."
	@$(PYTHON) scripts/gdrive_db_sync.py --pull
	@echo "[make analysis] Step 2: Running portfolio analysis (using cached data)..."
	@$(PYTHON) scripts/run_analysis.py
	@echo "[make analysis] Step 3: Pushing latest database to Google Drive..."
	@$(PYTHON) scripts/gdrive_db_sync.py --push

analysis-refresh:
	@echo "[make analysis] Step 1: Pulling latest database from Google Drive..."
	@$(PYTHON) scripts/gdrive_db_sync.py --pull
	@echo "[make analysis] Step 2: Running portfolio analysis with forced live refresh..."
	@$(PYTHON) scripts/run_analysis.py --force-refresh
	@echo "[make analysis] Step 3: Pushing latest database to Google Drive..."
	@$(PYTHON) scripts/gdrive_db_sync.py --push
dashboard:
	@echo "Computing dashboard overview and performance time-series..."
	@$(PYTHON) scripts/run_dashboard.py

projections:
	@echo "Running portfolio wealth and growth projections..."
	@$(PYTHON) scripts/run_projections.py

gdrive-push:
	@echo "Pushing database and JSON configs to Google Drive..."
	@$(PYTHON) scripts/gdrive_db_sync.py
	@$(PYTHON) scripts/gdrive_jsons_sync.py

gdrive-pull:
	@echo "Pulling latest database and JSON configs from Google Drive..."
	@$(PYTHON) scripts/gdrive_db_sync.py --pull

report: report-md

report-html:
	@$(PYTHON) scripts/generate_portfolio_report.py html

report-md:
	@$(PYTHON) scripts/generate_portfolio_report.py md

clean:
	@rm -rf reports/ build/ dist/ *.egg-info
	@rm -f data/.temp_snapshot.json
	@echo "[make clean] Temporary files and build artifacts cleaned."

lint:
	@echo "[make lint] Running ruff lint..."
	@$(RUFF) check .
	@echo "[make lint] Running ruff format check..."
	@$(RUFF) format --check .
	@echo "[make lint] Running mypy..."
	@$(MYPY) .

format:
	@echo "Formatting code with ruff..."
	@$(RUFF) format .

security:
	@echo "Running bandit security scan..."
	@$(BANDIT) -r config.py infra/ scripts/ -ll || true

mypy:
	@echo "Running mypy type checking..."
	@$(MYPY) .

migrate:
	@echo "[make migrate] Reconciling portfolio seed JSON into SQLite database..."
	@$(PYTHON) scripts/migrate_json_to_sqlite.py
