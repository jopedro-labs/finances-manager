# finances-manager

AI-driven investment portfolio manager. All analysis, scoring and report generation is handled by Google Gemini API — there is no Python engine for that logic.

## Goal

Manage and monitor a portfolio of stocks and ETFs:
- Capture snapshots from XTB screenshots stored in `input/`
- Quantitative and qualitative analysis based on defined rules
- Daily reports in HTML or Markdown

## Main flow

```
input/ (XTB screenshot) → make snapshot → extractor → snapshot → snapshots/snapshots.json + GDrive
make report             → analyst → reporter → HTML/MD report
```

## File map

| File / Path                            | Description                                                                          |
|----------------------------------------|--------------------------------------------------------------------------------------|
| `input/`                               | Drop XTB screenshots here before running `make snapshot` (gitignored)                |
| `secrets/`                             | Secure folder for credentials (`credentials.json`) and session tokens (`token.json`) |
| `data/portfolio.json`                  | Current holdings — asset_type, tickers, qty, average buy price, xtb_name             |
| `data/portfolio_targets.json`          | Target allocations (%) per asset                                                     |
| `snapshots/snapshots.json`             | Historical snapshot database with P&L, market values, allocations                    |
| `data/rules.md`                        | Business rules: scoring, decision matrix, projections, governance protocol           |
| `infra/logger.py`                      | Structured logger for consistent terminal/file output with contextual prefixes       |
| `infra/utils/file_utils.py`            | Safe text file loading utility with error handling and encoding fallback             |
| `scripts/extract_with_gemini.py`       | Extracts positions from XTB screenshot via Gemini Vision → triggers snapshot.py      |
| `scripts/snapshot.py`                  | Reads temp JSON → appends snapshots.json → syncs to GDrive                           |
| `scripts/generate_portfolio_report.py` | Calls Gemini with analyst + reporter instructions → saves report to reports/         |
| `reports/`                             | Generated reports (gitignored) — YYYY-MM-DD.md or YYYY-MM-DD.html                    |
| `config.py`                            | pydantic-settings Settings: paths + GDrive folder IDs + Gemini config                |
| `infra/gdrive/`                        | OAuth2 auth (gdrive_auth.py) + GDriveService wrapper (upload/download/backup)        |

## Available agents

| Agent       | Triggered by       | Responsibility                                           |
|-------------|--------------------|----------------------------------------------------------|
| `extractor` | `make snapshot`    | Extracts structured data from XTB screenshot in `input/` |
| `snapshot`  | `make snapshot`    | Calculates totals, persists snapshot, syncs GDrive       |
| `analyst`   | `make report`      | Applies rules.md — scores, recommendations, projections  |
| `reporter`  | `make report`      | Generates HTML or Markdown report with 3 sections        |

## Available commands

```bash
make snapshot       # capture new portfolio state (reads screenshot from input/)
make report         # generate daily report — saved to reports/YYYY-MM-DD.md
make report-html    # generate report as HTML — saved to reports/YYYY-MM-DD.html
make report-md      # generate report as Markdown — saved to reports/YYYY-MM-DD.md (alias)
```

## Collaboration rules

- Python scripts handle data extraction, persistence and GDrive sync — all scoring, analysis and report generation is done by Gemini
- Before editing any file on Google Drive, follow the governance protocol in Section 6 of `data/rules.md` (show changes → request authorisation → execute)
- The `market_value_eur` and `net_profit_eur` values from XTB are **sovereign** — never recalculate them from external quotes
- For cost calculations: `total_cost_eur = market_value_eur - net_profit_eur`

## Initial setup

1. Copy `.env.example` to `.env` and fill in `GEMINI_API_KEY` and the Google Drive folder IDs
2. Place `credentials.json` in `secrets/` for Google Drive OAuth2 authentication
3. On first run of `make snapshot`, a browser window will open to authorize access — `token.json` is saved automatically to `secrets/`

```bash
pip install -e .
```

Minimum dependencies: `google-genai`, `google-api-python-client`, `google-auth-oauthlib`, `pydantic-settings`.
