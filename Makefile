.PHONY: help snapshot analysis analysis-refresh dashboard projections quality quality-refresh gdrive-push gdrive-pull report report-html report-md clean lint security

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
	@echo "  make clean            - Remove generated files (reports/, temp snapshot)"
	@echo "  make lint             - Run ruff (lint + format check) and mypy (type check)"
	@echo "  make security         - Run bandit security scan"

snapshot:
	@echo "Processing XTB screenshot with Gemini Vision..."
	@$(PYTHON) scripts/extract_with_gemini.py
	@$(PYTHON) scripts/run_snapshot.py

analysis:
	@echo "Running portfolio analysis (using cached data)..."
	@$(PYTHON) scripts/run_analysis.py

analysis-refresh:
	@echo "Running portfolio analysis with forced live refresh..."
	@$(PYTHON) scripts/run_analysis.py --force-refresh

dashboard:
	@echo "Computing dashboard overview and performance time-series..."
	@$(PYTHON) scripts/run_dashboard.py

projections:
	@echo "Running portfolio wealth and growth projections..."
	@$(PYTHON) scripts/run_projections.py

quality:
	@echo "Evaluating stock and ETF fundamental quality tiers..."
	@$(PYTHON) scripts/run_quality.py

quality-refresh:
	@echo "Evaluating fundamental quality tiers with forced live refresh..."
	@$(PYTHON) scripts/run_quality.py --force-refresh

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
	@rm -rf reports/
	@rm -f data/.temp_snapshot.json
	@echo "Temporary files cleaned."

lint:
	@echo "Running ruff lint..."
	@$(RUFF) check .
	@echo "Running ruff format check..."
	@$(RUFF) format --check .
	@echo "Running mypy..."
	@$(MYPY) .

security:
	@echo "Running bandit security scan..."
	@$(BANDIT) -r config.py infra/ scripts/ -ll || true
```[cite: 20]