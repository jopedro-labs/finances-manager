# finances-manager

AI-driven investment portfolio manager powered by Google Gemini. Captures portfolio snapshots from XTB screenshots, applies quantitative scoring rules, and generates daily analysis reports in HTML or Markdown.

---

## Overview

The system is built around two independent pipelines:

**Snapshot pipeline** — sends an XTB "Open Positions" screenshot to Gemini Vision, extracts structured position data, calculates totals and allocation gaps, and appends the result to a historical log synced to Google Drive.

**Report pipeline** — reads the historical snapshot data, applies the scoring and allocation rules defined in `data/rules.md`, and produces a structured report with KPIs, per-asset recommendations, and long-term projections.

All analysis logic runs inside Gemini agents. There is no Python engine for scoring or recommendations — Python handles only extraction, persistence, and infrastructure.

---

## Architecture

```
input/ (XTB screenshot)
    └── make snapshot
            ├── scripts/extract_with_gemini.py   ← Gemini Vision extraction
            └── scripts/snapshot.py              ← persists + GDrive sync
                    └── snapshots/snapshots.json

snapshots/snapshots.json
    └── make report
            └── scripts/generate_portfolio_report.py   ← Gemini analysis
                    └── reports/YYYY-MM-DD.md / .html
```

### Gemini Agents (`.gemini/agents/`)

| Agent       | Responsibility                                                        |
|-------------|-----------------------------------------------------------------------|
| `extractor` | Reads the XTB screenshot and extracts structured position data        |
| `run_snapshot.py`  | Calculates totals, allocations, costs and persists the snapshot       |
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
| `snapshots/snapshots.json`             | Historical snapshot log with P&L, market values and allocations            |
| `scripts/extract_with_gemini.py`       | Gemini Vision extraction → writes temp JSON → triggers `run_snapshot.py`       |
| `scripts/run_snapshot.py`                  | Reads temp JSON → appends `snapshots.json` → syncs to GDrive               |
| `scripts/generate_portfolio_report.py` | Calls Gemini with analyst + reporter instructions → saves report           |
| `reports/`                             | Generated reports — `YYYY-MM-DD.md` or `YYYY-MM-DD.html` (gitignored)     |
| `config.py`                            | Centralised settings via pydantic-settings (paths + env vars)              |
| `infra/gdrive/`                        | Google Drive OAuth2 integration (upload, download, sync)                   |
| `infra/logger/`                        | ANSI-coloured terminal logger (`logger` singleton)                         |
| `infra/utils/`                         | File I/O utilities (`load_file_content`)                                   |
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

### Capture a snapshot

Place an XTB "Open Positions" screenshot in `input/` then run:

```bash
make snapshot
```

This sends the screenshot to Gemini Vision, extracts position data, calculates totals and allocation gaps against targets, and appends the result to `snapshots/snapshots.json`, syncing to Google Drive.

### Generate a report

```bash
make report       # Markdown — saved to reports/YYYY-MM-DD.md
make report-html  # HTML     — saved to reports/YYYY-MM-DD.html
make report-md    # Markdown — alias for make report
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
