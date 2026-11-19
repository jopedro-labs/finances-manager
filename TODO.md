# TODO — finances-manager

## High Priority (Bugs, Inconsistencies & Critical Fixes)

### 1. Leverage Threshold Calibration (Debt/Equity) and Unit Normalization
- **Context:** In `evaluate_stock_quality` (`core/analysis.py`), the `totalDebtToEquity` ratio is evaluated against bands misaligned with conservative market standards (e.g., Eli Lilly `LLY` with D/E of ~122.9% triggers no risk flag because it falls within the `<= 150.0%` band). Furthermore, different data sources (Yahoo Finance vs. JustETF vs. financial statements) may return values as percentages (122.9) or raw decimals (1.229).
- **Action Items:**
  - [ ] Calibrate the upper bound for moderate leverage down from 150% to 100% (or 120%), triggering a risk warning under `bear_points` whenever exceeded.
  - [ ] Add dedicated unit tests for D/E ratio normalization and threshold boundaries to prevent false-positive Tier A classifications.

---

### 2. Cache Semantics and `--force-refresh` Cascading
- **Context:** When running `make analysis-refresh` or `make quality-refresh`, the scripts log `"forced live refresh"`, but internal lookups in `StockProvider` and `ETFProvider` may still retrieve records from SQLite cache if lower-level cache layers are not explicitly bypassed.
- **Action Items:**
  - [ ] Ensure the `--force-refresh` flag propagates end-to-end, cleanly bypassing both SQLite cache (`asset_fundamentals`) and JSON cache (`data/etf_cache.json`).
  - [ ] Align terminal log output with actual execution semantics (clearly distinguishing live network fetches from cache hits within TTL).

---

### 3. Daily Execution Idempotency & Test Hygiene in `opportunities`
- **Context:** Running multiple analysis executions on the same calendar day inserts new records with second-by-second timestamps into `opportunities` and `opportunity_asset_metrics`, accumulating redundant runs that unnecessarily bloat the SQLite database.
- **Action Items:**
  - [ ] Implement a same-day upsert or replacement policy (`DATE(timestamp) = CURRENT_DATE`), maintaining a clean history of exactly one opportunity analysis run per day.
  - [ ] Ensure all automated tests run strictly against ephemeral, isolated databases (`:memory:` or `tmp_path`), preventing data pollution and locking issues on `data/finances.db`.

---

## Medium Priority (Testing & Code Coverage)

### 4. Expansion of Unit and Integration Test Suite
- **Context:** Currently, only `tests/test_scoring.py` is present. Crucial modules of the deterministic computation engine and database persistence lack automated test coverage.
- **Action Items:**
  - [ ] Create `tests/test_exposure.py` to validate look-through sector allocation (including normalization via `SECTOR_ALIASES`), country breakdown, and underlying ETF company exposures.
  - [ ] Create `tests/test_quality_eval.py` to validate knockout rules and tier classification (Tier A, B, and C) across both Stocks and ETFs.
  - [ ] Create `tests/test_projections.py` to validate compound growth math, inflation adjustments, and 10/20/30-year horizon scenarios.
  - [ ] Create `tests/test_sqlite_repositories.py` to test persistence, schema migrations, and SQL extraction using in-memory SQLite (`:memory:`).
  - [ ] Add code coverage enforcement in CI using `pytest-cov` (target: `>= 80%` on core modules).

---

### 5. Resilience of XTB Screenshot Extraction Pipeline
- **Context:** `scripts/extract_xtb_open_positions.py` relies on a hardcoded path (`input/xtb_screenshot.png`). If the user drops an image with a different name or extension (`.jpg`, `.jpeg`, or timestamped filenames), the script immediately aborts.
- **Action Items:**
  - [ ] Update `get_screenshot_path()` to dynamically detect the most recent image in `input/` (`*.png`, `*.jpg`, `*.jpeg`), sorting by file modification time.
  - [ ] Add pre-flight image integrity validation before invoking the Gemini Vision API.

---

## Future Enhancements & Features (Backlog)

### 6. Automated Alerts & Notifications
- **Context:** Reports are generated locally in `reports/`. There is currently no direct broadcast channel to alert the user upon completion.
- **Action Items:**
  - [ ] Implement a webhook service to dispatch daily execution digests (KPIs, exposure limit breaches, top BUY recommendations) via Discord or Telegram.
  - [ ] Add a `--notify` flag to `make snapshot` and `make analysis`.

---

### 7. XTB Broker Metric Enrichment
- **Context:** Broker fields currently omitted from persistence:
  - Financing and swap costs (`swap`)
  - Accumulated trading commissions (`commission`)
  - Order execution timestamp (`open_time`) for precise holding period tracking and capital gains tax analysis.
- **Action Items:**
  - [ ] Evaluate expanding `asset_snapshots` schema to store fees and commissions when provided by the broker export.