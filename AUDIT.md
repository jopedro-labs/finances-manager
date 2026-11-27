# Codebase Audit Report: `finances-manager`

## Executive Summary

This document provides a factual, comprehensive audit of the `finances-manager` repository on branch `chore/config-restore-local-env-audit`. It documents missing local runtime artifacts, environment configuration gaps, Google Drive remote architecture, `rclone` integration status, bugs and fragilities across scripts and core modules, and test coverage deficiencies.

The project serves as the core orchestration, valuation, and reporting engine for personal portfolio management, integrating with Google Gemini AI for broker position extraction and Google Drive for remote persistence.

---

## 1. Missing Local Files & Environment Setup

- [x] **Stale/Mismatched `AUDIT.md` Reference**:
  - The repository's untracked `AUDIT.md` previously contained a verbatim copy of `core-lib`'s `TODO.md` mentioning Discord dynamic exports and GDrive mutants, unrelated to `finances-manager`.
  - Acceptance Criteria: Replace with a dedicated, structured audit report tailored to `finances-manager`.

- [x] **Missing Root `.env` Configuration**:
  - The local `.env` file does not exist upon clean clone. Required configuration parameters (Gemini API key, Google Drive folder IDs, database path) are absent from local execution context.
  - Acceptance Criteria: Recreate `.env` locally using verified credentials and remote folder identifiers.

- [x] **Discrepancies in `.env.example` Configuration Template**:
  - `GDRIVE_XTB_OPEN_POSITIONS_FOLDER_ID` is parsed in `config.py` (line 46) but is omitted from `.env.example`.
  - `SNAPSHOT_FRESHNESS_HOURS` is declared in `config.py` (line 91) but missing from `.env.example`.
  - Parameter names for credentials in `config.py` (`GDRIVE_CREDENTIALS_FILE`, `GDRIVE_TOKEN_FILE`) differ from `core_lib` conventions (`GDRIVE_CREDENTIALS_PATH`, `GDRIVE_TOKEN_PATH`).
  - `rclone` remote sync variables (`RCLONE_REMOTE_NAME`, `RCLONE_REMOTE_DATA_PATH`, `RCLONE_REMOTE_SNAPSHOTS_PATH`) are not documented.
  - `INFRA_ALERTS_DISCORD_WEBHOOK` is used across companion libraries (`core_lib`) but unreferenced in template.
  - Acceptance Criteria: Update `.env.example` with all variables, clear documentation, and defaults.

- [x] **Missing Local Runtime Directories and Artifacts**:
  - `secrets/`: Local directory for Google OAuth2 credentials (`secrets/credentials.json`, `secrets/token.json`) is not initialized.
  - `input/`: Directory for broker screenshots (`input/xtb_screenshot.png`) is untracked and uninitialized.
  - `reports/`: Target output folder for generated Markdown/HTML daily reports is untracked.
  - `data/finances.db`: Primary SQLite database is absent locally.
  - `data/portfolio.json` & `data/portfolio_targets.json`: Seed asset lists are absent locally due to gitignore rule `data/*.json`.
  - Acceptance Criteria: Initialize local folder structures (`secrets/`, `input/`, `reports/`, `data/`) and safely restore database and configuration files.

- [x] **Remote Google Drive Architecture & Rclone Status**:
  - `rclone` CLI executable is not installed on the system (`Exit Code 127`), and no configuration exists at `~/.config/rclone/`.
  - Inspection of Google Drive remote storage via `core_lib.gdrive.GDriveService` revealed the following hierarchy:
    - Root project folder: `1ZWwNGKrLyBz-91CZV8FQvXRuNJ-iPCrv`
    - Data subfolder (`GDRIVE_DATA_FOLDER_ID`): `1FrsIRkosCKqtZ5qm7cIRttYP_fdQpfWD` (hosts `portfolio.json`, `portfolio_targets.json`, `etf_cache.json`)
    - Snapshots subfolder (`GDRIVE_SNAPSHOTS_FOLDER_ID`): `1SaP9Tklp2BJRBeKnWpaUo1eLl9ekcKmj` (hosts active `finances.db` with latest snapshot `2026-11-19T13:51:08Z`, total market value €3,361.35)
  - Acceptance Criteria: Document Google Drive folder mapping and ensure sync scripts target the exact subfolders.

- [x] **Gaps in `.gitignore`**:
  - `.gitignore` ignores `data/*.db` and `data/*.json`, but lacks explicit exclusion guards for SQLite temporary journal files (`*.db-shm`, `*.db-wal`), general `.env.*` variants, and runtime log files (`*.log`, `logs/`).
  - Missing explicit un-ignore for `!.env.example`.
  - Acceptance Criteria: Harden `.gitignore` to prevent secret leakage and keep `.env.example` tracked.

---

## 2. Bugs & Code Fragilities

- [x] **`Makefile` Google Drive Pull Incompleteness**:
  - In `Makefile`, `make gdrive-push` correctly executes both `scripts/gdrive_db_sync.py` and `scripts/gdrive_jsons_sync.py`.
  - However, `make gdrive-pull` only runs `scripts/gdrive_db_sync.py --pull`, omitting `scripts/gdrive_jsons_sync.py --pull`. This leaves local `data/portfolio.json` and `data/portfolio_targets.json` un-synchronized after a fresh clone.
  - Acceptance Criteria: Update `Makefile` `gdrive-pull` target to pull both database and JSON configurations.

- [x] **Missing Makefile Targets (`install`, `check`, `validate-audit`, `test`)**:
  - `Makefile` lacked `install`, `check`, and `validate-audit` targets, requiring manual invocation of tools.
  - Acceptance Criteria: Add `make install` (`pip install -e ".[dev]"`), `make test`, `make validate-audit`, and `make check`.

- [x] **Logging Standard Violation in `scripts/extract_xtb_open_positions.py`**:
  - Line 154 invokes `print(result)` printing an unformatted raw Python dictionary to STDOUT instead of using `core_lib.logger` or structured JSON serialization.
  - Acceptance Criteria: Replace raw `print(result)` with structured logging or valid JSON stdout piping.

- [x] **Silent Failure in `scripts/migrate_json_to_sqlite.py`**:
  - When `data/portfolio.json` is missing, `migrate_portfolio_to_sqlite()` logs an error and returns with exit code 0 instead of terminating with non-zero exit code (`sys.exit(1)`), causing automated Makefile pipelines to report success when migration failed.
  - Acceptance Criteria: Exit with code 1 if the required portfolio seed file is missing.

- [x] **Potential Unhandled Exception in `core/currency_exchange.py`**:
  - In `get_exchange_rate()`, `float(hist["Close"].iloc[-1])` executes without verifying whether the closing price is `NaN` or unaligned.
  - Exception logging uses `logger.error(str(err), exception=e)`, which causes keyword mismatch in standard loggers.
  - Acceptance Criteria: Add `pd.isna` verification and use standard logging syntax.

- [x] **CI Workflow Modernization to `ci.yml` (`core-lib` alignment)**:
  - Replaced legacy `.github/workflows/lint.yml` with `.github/workflows/ci.yml` matching `core-lib`.
  - Modernized runner installation to `python -m pip install --upgrade pip && pip install -e ".[dev]"`, resolving `ModuleNotFoundError: No module named 'core_lib'` on GitHub Actions runners.
  - Executes `ruff check .`, `ruff format --check .`, `mypy .`, `pytest --tb=short`, and `python scripts/validate_audit_sync.py --enforce-sync`.

- [x] **Missing AUDIT Integrity & Sync Script (`scripts/validate_audit_sync.py`)**:
  - Introduced `scripts/validate_audit_sync.py` and accompanying test suite `tests/test_validate_audit_sync.py` to enforce required section headers and sync coherence across monitored paths.
  - Acceptance Criteria: Implement and test audit verification tool.

- [x] **Missing Direct Dependencies & Dev Dependencies in `pyproject.toml`**:
  - Direct imports of `python-dotenv` and `pydantic` were not explicitly listed in `[project.dependencies]`.
  - Development tools (`pytest`, `pytest-cov`, `ruff`, `mypy`, `bandit`) were not specified under `[project.optional-dependencies.dev]`.
  - Acceptance Criteria: Declare direct and development dependencies explicitly in `pyproject.toml`.

- [x] **Documentation Drift in `README.md`**:
  - `README.md` omitted development installation instructions (`pip install -e ".[dev]"`), lacked `make test` and `pytest` documentation in the quality section, and had incomplete requirements listings.
  - Acceptance Criteria: Update `README.md` to accurately document current commands, quality gates, and prerequisites.

---

## 3. Test Coverage Gaps

- [x] **Type Safety and Formatting Errors in Existing Test Files**:
  - `tests/test_package_exports.py`: Missing `from __future__ import annotations`, missing return type annotations (`-> None`), triggering `mypy [no-untyped-def]` errors.
  - `tests/test_gdrive_service_extended.py`: Missing type annotations on fixtures and test parameters (`service: GDriveService`, `tmp_path: Path`), unused imports (`pathlib.Path`), and docstrings written in Portuguese violating English repository standards.
  - Acceptance Criteria: Fix all type annotations and linting in existing tests.

- [x] **Core Configuration, Connection, Projections & Audit Sync Unit Testing**:
  - Added unit test suites verifying foundational behaviors:
    - `tests/test_config.py`: Validates default settings, environment overrides, and folder ID sanitization.
    - `tests/test_database_connection.py`: Verifies PRAGMA foreign keys, row factory, and transactional commits/rollbacks.
    - `tests/test_projections.py`: Tests compound interest formula, linear zero-rate edge cases, and 10/20/30-year scenario milestones.
    - `tests/test_validate_audit_sync.py`: Validates AUDIT.md structural verification and bypass flags.
  - Acceptance Criteria: Implement unit test suites ensuring strict typing and passing all quality gates.

- [ ] **Remaining Modules Awaiting Regression Coverage**:
  - `infra/database/schema.py`: Zero tests for `initialize_database()` DDL execution and migration idempotence.
  - `infra/database/finance_sql_extraction.py`: Zero tests for SQL query construction, allowlist enforcement, and historical record parsing.
  - `core/exposure.py`: Zero tests for look-through aggregation across ETFs and direct stocks.
  - `core/analysis.py` & `core/portfolio_analytics.py`: Zero tests for performance metrics and Sharpe ratio calculations.
  - `core/repositories.py`: Zero tests for `SqlitePortfolioRepository`, `SqliteHistoryRepository`, and fundamental repositories.
  - All 10 pipeline scripts in `scripts/`: Zero automated regression verification.
