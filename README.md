# finances-manager

![Python 3.13+](https://img.shields.io/badge/python-3.13+-3776AB?style=flat-square&logo=python&logoColor=white)
![Version](https://img.shields.io/badge/version-0.1.0-58a6ff?style=flat-square)
![Lint Workflow](https://github.com/jopedro-labs/finances-manager/actions/workflows/lint.yml/badge.svg)
![SQLite](https://img.shields.io/badge/database-SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)
<br />
![Linter](https://img.shields.io/badge/linter-Ruff-000000?style=flat-square&logo=python&logoColor=white)
![Type Check](https://img.shields.io/badge/types-mypy%20strict-2A6DB2?style=flat-square&logo=python&logoColor=white)
![Security](https://img.shields.io/badge/security-Bandit-black?style=flat-square)
![Gemini AI](https://img.shields.io/badge/Gemini_AI-8E75B2?style=flat-square&logo=googlegemini&logoColor=white)
![GNU Make](https://img.shields.io/badge/env-GNU%20Make-active?style=flat-square&logo=gnu-make&logoColor=white)
![MIT License](https://img.shields.io/badge/license-MIT-607D8B?style=flat-square)

AI-driven investment portfolio manager powered by Google Gemini. Captures portfolio snapshots from XTB screenshots, applies quantitative scoring rules, and generates daily analysis reports in HTML or Markdown.

---

## Overview

The system is built around three integrated pipelines:

**Snapshot pipeline** — sends an XTB "Open Positions" screenshot to Gemini Vision, extracts structured position data, calculates totals and allocation gaps, persists the snapshot into the local SQLite database (`data/finances.db`), and backs it up to Google Drive.

**Quality & Analytics pipeline** — evaluates fundamental quality tiers (Tier A/B/C) for stocks and ETFs (`make quality`), analyzes overall portfolio ROI, exposures, and historical performance (`make analysis`), generating structured reports in `reports/`.

**Report pipeline** — reads historical snapshot and fundamental data, applies the scoring and allocation rules defined in `data/rules.md`, and produces a structured AI report with KPIs, per-asset recommendations, and long-term projections (`make report`).

The system combines a deterministic Python engine for exact P&L, exposure calculations, and fundamental scoring with Gemini agents for multimodal vision extraction and narrative intelligence.

---

## Architecture

```
input/ (XTB screenshot)
    └── make snapshot
            ├── scripts/extract_xtb_open_positions.py   ← Gemini Vision extraction
            └── scripts/run_snapshot.py                 ← persists to SQLite + GDrive backup
                    └── data/finances.db

data/finances.db
    ├── make quality       → scripts/run_quality.py               → reports/quality_report.md
    ├── make analysis      → scripts/run_analysis.py              → reports/analysis_report.md
    ├── make dashboard     → scripts/run_dashboard.py             → reports/dashboard_report.md
    ├── make projections   → scripts/run_projections.py           → reports/projections_report.md
    └── make report        → scripts/generate_portfolio_report.py → reports/YYYY-MM-DD.md / .html
```

### Gemini Agents (`.gemini/agents/`)

| Agent       | Responsibility                                                        |
|-------------|-----------------------------------------------------------------------|
| `extractor` | Reads the XTB screenshot and extracts structured position data        |
| `analyst`   | Applies `data/rules.md` — scores, tiers, recommendations, projections |
| `reporter`  | Renders the final report in HTML or Markdown                          |

---

## File Map

| Path                                   | Description                                                                |
|----------------------------------------|----------------------------------------------------------------------------|
| `input/`                               | Drop XTB "Open Positions" screenshots here before running `make snapshot`  |
| `data/portfolio.json`                  | Master list of holdings — ISIN, tickers, quantity, average buy price       |
| `data/portfolio_targets.json`          | Target allocation (%) per asset — drives rebalancing scores                |
| `data/rules.md`                        | Business rules: scoring formulas, decision matrix, projections, governance |
| `data/finances.db`                     | SQLite database: master assets, snapshots, fundamental history, and cache  |
| `scripts/extract_xtb_open_positions.py`| Gemini Vision extraction → parses positions from input screenshot          |
| `scripts/run_snapshot.py`              | Persists structured snapshot to SQLite `finances.db` → syncs to GDrive     |
| `scripts/run_quality.py`               | Fundamental quality tier evaluation (Tier A/B/C) + quality report generator|
| `scripts/run_analysis.py`              | Opportunity scoring, policy exposure caps validation & analysis report      |
| `scripts/run_dashboard.py`             | Portfolio ATH, maximum drawdowns, time-series metrics & dashboard report   |
| `scripts/run_projections.py`           | Multi-horizon compound growth and wealth accumulation simulations          |
| `scripts/generate_portfolio_report.py` | Calls Gemini with analyst + reporter instructions (or deterministic engine) |
| `scripts/gdrive_db_sync.py`            | SQLite database synchronization with Google Drive (`--push` / `--pull`)    |
| `scripts/gdrive_jsons_sync.py`         | JSON configs synchronization with Google Drive (`--push` / `--pull`)      |
| `scripts/migrate_json_to_sqlite.py`    | Portfolio configuration seed reconciliation into SQLite database           |
| `reports/`                             | Generated reports — `YYYY-MM-DD.md`, `.html`, `quality_report.md`, etc.    |
| `config.py`                            | Centralised settings via pydantic-settings (paths + env vars)              |
| `stubs/`                               | Local type stubs for untyped third-party libraries                         |
| `.env`                                 | Local environment variables (not committed)                                |
| `secrets/`                             | OAuth2 credentials (`credentials.json`) and session token (`token.json`)   |

---

## Setup

### 1. Install dependencies

```bash
pip install -e .
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```env
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.8-flash

GDRIVE_DATA_FOLDER_ID=your_gdrive_folder_id
GDRIVE_SNAPSHOTS_FOLDER_ID=your_gdrive_snapshots_folder_id
```

### 3. Configure Google Drive (OAuth2)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project
2. Enable the **Google Drive API**
3. Create an **OAuth 2.0 Client ID** (application type: Desktop app)
4. Download the JSON key and place it at `secrets/credentials.json`
5. On the first `make snapshot` run, a browser window will open to authorise access — `secrets/token.json` is saved automatically for subsequent runs

---

## Usage

### 1. Capture a snapshot

Place an XTB "Open Positions" screenshot in `input/` then run:

```bash
make snapshot
```

This sends the screenshot to Gemini Vision, extracts position data, calculates totals and allocation gaps against targets, appends the result to SQLite (`data/finances.db`), and syncs to Google Drive.

### 2. Run Fundamental Quality Audit

```bash
make quality          # Evaluates fundamental metrics and generates reports/quality_report.md
make quality-refresh  # Forces live API fetch bypassing local cache
```

### 3. Run Portfolio Performance & Opportunity Analysis

```bash
make analysis         # Evaluates performance, exposure limits and generates reports/analysis_report.md
make analysis-refresh # Forces live refresh before running performance analysis
```

### 4. Run Dashboard Metrics & Time-Series

```bash
make dashboard        # Computes ATH, drawdowns, asset class evolution and reports/dashboard_report.md
```

### 5. Run Long-Term Wealth Projections

```bash
make projections      # Simulates 10/20/30-year compound growth and generates reports/projections_report.md
```

### 6. Generate AI Portfolio Report

```bash
make report       # Markdown — saved to reports/YYYY-MM-DD.md
make report-html  # HTML     — saved to reports/YYYY-MM-DD.html
make report-md    # Markdown — alias for make report
```

### 7. Google Drive Synchronization

```bash
make gdrive-pull  # Pull latest database and JSON configs from Google Drive
make gdrive-push  # Push local database and JSON configs to Google Drive
```

### 8. Database Reconciliation & Migration

```bash
make migrate      # Reconciles assets from data/portfolio.json into the SQLite database
```

---

## Report Structure

Every report contains three mandatory sections:

**Section 1 — Macro Summary**
Portfolio KPIs (total market value, invested capital, unrealised P&L), exposure breakdown by country and sector, and recent historical evolution.

**Section 2 — Holdings & Recommendations**
Per-asset table sorted by score (descending), showing quantity, cost, current value, allocation gap and a colour-coded recommendation badge: `BUY`, `HOLD`, `HOLD/REBAL`, or `SELL`. Active positions and watchlist items are visually separated.

**Section 3 — Projections**
3×3 scenario matrix across 10, 20 and 30-year horizons at conservative (5%), realistic (8%) and optimistic (11%) annual returns, based on current market value and optional monthly contributions.

---

## Scoring Model

### Stocks

| Criterion                             | Weight |
|---------------------------------------|--------|
| Dip Score (discount from recent peak) | 25%    |
| Forward P/E Growth Multiplier         | 25%    |
| 52-Week Range Positioning             | 15%    |
| Allocation Gap                        | 35%    |

### ETFs

| Criterion             | Weight |
|-----------------------|--------|
| Dip Score             | 30%    |
| Cost Efficiency (TER) | 20%    |
| Allocation Gap        | 50%    |

### Exposure Limits

| Limit                      | Ceiling |
|----------------------------|---------|
| Per country                | 60%     |
| Technology sector          | 50%     |
| Other individual sectors   | 20%     |
| Per company (look-through) | 15%     |

Violations apply score penalty multipliers to affected assets.

---

## Data Governance

- `market_value_eur` and `net_profit_eur` from XTB are **sovereign** — never recalculated from external quotes
- `total_cost_eur = market_value_eur − net_profit_eur` (derived from broker data, captures real FX at acquisition)
- Before editing any file on Google Drive, follow the governance protocol in Section 6 of `data/rules.md`

---

## Code Quality

```bash
make lint      # ruff (lint + format) + mypy (strict type check)
make security  # bandit static security scan
```

| Tool   | Purpose                        | Config            |
|--------|--------------------------------|-------------------|
| ruff   | Linting, import sorting, style | `pyproject.toml`  |
| mypy   | Static type checking (strict)  | `pyproject.toml`  |
| bandit | Security vulnerability scan    | CLI flags         |

A GitHub Actions workflow (`.github/workflows/lint.yml`) runs `make lint` on every push and pull request.

---

## Requirements

- Python 3.13+
- `google-genai` — Gemini API client
- `google-api-python-client` + `google-auth-oauthlib` — Google Drive
- `pydantic-settings` — configuration management
