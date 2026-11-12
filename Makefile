.PHONY: snapshot report report-html report-md clean lint security help

PYTHON := .venv/bin/python3
RUFF   := .venv/bin/ruff
MYPY   := .venv/bin/mypy
BANDIT := .venv/bin/bandit
export PYTHONPATH := $(CURDIR)

help:
	@echo "Portfolio Manager -- Available commands:"
	@echo "  make snapshot       - Extract data from XTB screenshot in input/ and sync to GDrive"
	@echo "  make report         - Generate daily report as Markdown saved to reports/"
	@echo "  make report-html    - Generate report as HTML saved to reports/"
	@echo "  make report-md      - Generate report as Markdown saved to reports/ (alias)"
	@echo "  make clean          - Remove generated files (reports/, temp snapshot)"
	@echo "  make lint           - Run ruff (lint + format check) and mypy (type check)"
	@echo "  make security       - Run bandit security scan"

snapshot:
	@echo "Processing XTB screenshot with Gemini Vision..."
	@$(PYTHON) scripts/extract_with_gemini.py

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
