# infra/database

SQLite persistence layer for the finances-manager portfolio system.
Handles schema creation, connection management, idempotent migrations, and historical data extraction.

---

## Files

| File | Responsibility |
|---|---|
| `connection.py` | Connection factory and transactional context manager |
| `schema.py` | DDL definitions, performance indexes, and migration runner |
| `finance_sql_extraction.py` | Read-only historical data extraction with legacy schema compatibility |

---

## Architecture

```
connection.py          schema.py               finance_sql_extraction.py
─────────────          ─────────               ─────────────────────────
get_connection()   →   create_tables()         FinanceSQLExtractor
get_db_context()   →   apply_migrations()        └─ fetch_asset_history()
                   →   initialize_database()      └─ fetch_portfolio_history()
```

`initialize_database` is the single entry point for schema bootstrap. Callers (repositories, scripts) call it once on startup via `get_db_context`. The extractor is purely passive — it never modifies the schema.

---

## connection.py

### `get_connection(db_path, timeout) → sqlite3.Connection`

Opens a raw SQLite connection with:
- `sqlite3.Row` factory (column access by name)
- `PRAGMA foreign_keys = ON` enforced at the connection level
- Configurable lock timeout (default: `10.0s`) to handle concurrent write contention

Use this when you need manual transaction control.

### `get_db_context(db_path, timeout) → Generator[Connection]`

Context manager wrapping `get_connection`. Automatically:
- Commits on clean exit
- Rolls back on any exception
- Closes the connection in all scenarios (`finally`)

```python
with get_db_context() as conn:
    conn.execute("INSERT INTO assets ...")
# commit happens here automatically
```

> **Note:** DDL statements (`CREATE TABLE`, `ALTER TABLE`) committed mid-context cannot be rolled back by this manager if a subsequent operation fails. This is a SQLite limitation, not a bug.

### `DEFAULT_DB_PATH`

Public `Path` constant resolving to `settings.finance_db_file`. Evaluated eagerly at import time for compatibility with external callers. Internal functions (`get_connection`, `get_db_context`) resolve the path lazily via `_resolve_db_path()` — passing `None` as `db_path` always falls back to the current settings value.

---

## schema.py

### Tables

#### `assets`
Master registry of all portfolio holdings.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `isin` | TEXT | Optional, unique |
| `name` | TEXT NOT NULL | Human-readable name |
| `yahoo_ticker` | TEXT NOT NULL | Yahoo Finance symbol |
| `quantity` | REAL NOT NULL | Current units held |
| `average_buy_price` | REAL NOT NULL | Cost basis per unit |
| `asset_type` | TEXT NOT NULL | `STOCK` or `ETF` (CHECK constraint) |
| `xtb_name` | TEXT | XTB platform display name |
| `xtb_ticker` | TEXT | XTB platform ticker |
| `just_etf_ticker` | TEXT | JustETF ticker for ETF lookup |
| `native_currency` | TEXT NOT NULL | ISO 4217 code, default `EUR` |
| `created_at` | TIMESTAMP | Auto-set on insert |

#### `portfolio_snapshots`
Point-in-time portfolio valuations. One row per snapshot event.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `timestamp` | TEXT NOT NULL UNIQUE | ISO8601 snapshot timestamp |
| `total_invested_eur` | REAL NOT NULL | Total capital deployed |
| `total_market_value_eur` | REAL NOT NULL | Total market value at snapshot time |
| `unrealized_pnl_eur` | REAL NOT NULL | Stored for read performance — source of truth: `total_market_value_eur - total_invested_eur` |
| `unrealized_pnl_pct` | REAL NOT NULL | Stored for read performance — source of truth: `unrealized_pnl_eur / total_invested_eur * 100` |
| `currencies_rate_json` | TEXT | JSON dict of exchange rates used at snapshot time |
| `breakdown_json` | TEXT | JSON dict of allocation breakdown by asset |
| `is_baseline` | INTEGER NOT NULL | Boolean (0/1). Marks the reference snapshot for P&L baseline calculations |

> **Writers must always compute `unrealized_pnl_*` from sovereign XTB values before inserting** — never derive from external quotes.

#### `asset_snapshots`
Per-asset detail for each portfolio snapshot. Immutable historical record.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `snapshot_id` | INTEGER NOT NULL | FK → `portfolio_snapshots.id` ON DELETE CASCADE |
| `asset_id` | INTEGER NOT NULL | FK → `assets.id` ON DELETE CASCADE |
| `quantity` | REAL NOT NULL | Units held at exact snapshot moment |
| `invested_eur` | REAL NOT NULL | Capital deployed for this asset at snapshot time |
| `native_price` | REAL NOT NULL | Price in native currency at snapshot time |
| `native_currency` | TEXT NOT NULL | ISO 4217 currency code |
| `value_eur` | REAL NOT NULL | Market value converted to EUR |

Constraint: `UNIQUE (snapshot_id, asset_id)` — one row per asset per snapshot.

#### `stock_fundamental_history`
Time-series fundamental metrics for STOCK assets. One row per fetch per asset.

| Column | Type | Notes |
|---|---|---|
| `asset_id` | INTEGER NOT NULL | FK → `assets.id` |
| `fetched_at` | TEXT NOT NULL | ISO8601, CHECK format enforced |
| `market_cap` | REAL | |
| `pe_ratio` | REAL | Trailing P/E |
| `forward_pe` | REAL | |
| `price_to_book` | REAL | |
| `peg_ratio` | REAL | |
| `dividend_yield_pct` | REAL | |
| `return_on_equity_pct` | REAL | |
| `total_debt_to_equity` | REAL | |
| `free_cashflow` | REAL | |
| `beta` | REAL | |
| `eps_trailing_ttm` | REAL | |
| `fifty_two_week_high` | REAL | |
| `fifty_two_week_low` | REAL | |
| `sector` | TEXT | |
| `industry` | TEXT | |
| `quality_tier` | TEXT | Scoring tier (e.g. `A`, `B`, `C`) |
| `quality_score` | INTEGER | Numeric quality score |

#### `etf_fundamental_history`
Time-series fundamental metrics for ETF assets. One row per fetch per asset.

| Column | Type | Notes |
|---|---|---|
| `asset_id` | INTEGER NOT NULL | FK → `assets.id` |
| `fetched_at` | TEXT NOT NULL | ISO8601, CHECK format enforced |
| `ter_pct` | REAL | Total Expense Ratio |
| `fund_size_eur_m` | REAL | Fund AUM in millions EUR |
| `holdings_count` | INTEGER | Number of holdings |
| `volatility_1y_pct` | REAL | 1-year annualised volatility |
| `holdings_json` | TEXT | JSON list of top holdings |
| `sector_breakdown_json` | TEXT | JSON dict of sector weights |
| `country_breakdown_json` | TEXT | JSON dict of country weights |
| `quality_tier` | TEXT | |
| `quality_score` | INTEGER | |

#### `asset_fundamentals`
Latest-only fundamental cache. One row per asset (UNIQUE on `asset_id`).

Stores the most recent fetch as a JSON blob (`details_json`) alongside typed `quality_tier` and `quality_score`. Use this for current state lookups; use `stock_fundamental_history` / `etf_fundamental_history` for time-series analysis.

#### `opportunities`
Header record for each opportunity evaluation run.

| Column | Type | Notes |
|---|---|---|
| `timestamp` | TEXT NOT NULL UNIQUE | Run timestamp |
| `total_invested_eur` | REAL NOT NULL | Portfolio capital at run time |
| `total_value_eur` | REAL NOT NULL | Portfolio market value at run time |
| `unrealized_pnl_eur` | REAL NOT NULL | Derived from `total_value_eur - total_invested_eur` |
| `has_ai` | INTEGER NOT NULL | Boolean (0/1) — whether AI scoring was enabled |

#### `opportunity_asset_metrics`
Per-asset scores and AI recommendations for each opportunity run.

Key columns: `rank`, `dip_score`, `cost_score`, `gap_score`, `quant_score`, `risk_score`, `valuation_score`, `ai_action`, `ai_urgency`, `ai_confidence_pct`, `advisory_json`.

Constraint: `UNIQUE (opportunity_id, symbol)` — one row per asset per run.

---

### Indexes

| Index | Table | Columns | Purpose |
|---|---|---|---|
| `idx_asset_snapshots_snapshot_id` | `asset_snapshots` | `snapshot_id` | Join from snapshot to asset rows |
| `idx_asset_snapshots_asset_id` | `asset_snapshots` | `asset_id` | Join from asset to its snapshot history |
| `idx_opportunity_metrics_opp_id` | `opportunity_asset_metrics` | `opportunity_id` | Join opportunity → metrics |
| `idx_opportunity_metrics_rank` | `opportunity_asset_metrics` | `(opportunity_id, rank)` | Ranked lookup within a run |
| `idx_stock_fundamentals_lookup` | `stock_fundamental_history` | `(asset_id, fetched_at DESC)` | Latest fundamentals per stock |
| `idx_etf_fundamentals_lookup` | `etf_fundamental_history` | `(asset_id, fetched_at DESC)` | Latest fundamentals per ETF |
| `idx_assets_yahoo_ticker` | `assets` | `yahoo_ticker` | Ticker resolution without full scan |

### Functions

#### `create_tables(conn)`
Executes all DDL in topological dependency order (parents before children), then creates all indexes. Commits on success, rolls back on `sqlite3.Error`.

#### `apply_migrations(conn)`
Applies idempotent `ALTER TABLE` migrations for legacy databases. Each migration is guarded with `try/except OperationalError` narrowed to `"duplicate column name"` — any other error is re-raised. Column and type values are validated against explicit allowlists before interpolation. Commits on success, rolls back on failure.

#### `initialize_database(conn)`
Orchestrates `create_tables` → `apply_migrations`. This is the **single entry point** that callers should use. Safe to call on every startup — all operations are idempotent.

---

## finance_sql_extraction.py

Read-only. Never modifies the schema or data.

### Data structures

#### `AssetHistoricalRecord` (frozen dataclass)
One record per asset per snapshot. Fields: `snapshot_date`, `asset_ticker`, `asset_name`, `asset_type`, `quantity`, `value_eur`, `native_price` (default `0.0`), `native_currency` (default `"EUR"`).

#### `PortfolioHistoricalRecord` (frozen dataclass)
One record per snapshot. Fields: `snapshot_date`, `total_value_eur`.

### `FinanceSQLExtractor`

```python
extractor = FinanceSQLExtractor()                      # uses settings default path
extractor = FinanceSQLExtractor("data/finances.db")    # explicit path

history = extractor.fetch_asset_history()       # list[AssetHistoricalRecord]
totals  = extractor.fetch_portfolio_history()   # list[PortfolioHistoricalRecord]
```

Both methods return `[]` gracefully in all of these scenarios:
- Database file does not exist
- Database exists but has not been initialised (tables missing)
- Database is initialised but contains no records

### SQL injection defence

All dynamic column and table references follow a two-layer defence:

1. **`_get_table_name`** — resolves table name from `sqlite_master` against an ordered candidate list. Raises `ValueError` if none exist.
2. **`_get_column_name`** — resolves column name via `PRAGMA table_info`. Raises `ValueError` if none exist.
3. **`_safe_col`** — validates the resolved name against a `frozenset` allowlist before interpolation into the query string.

No user-supplied values are ever interpolated into SQL. All interpolated identifiers are either resolved from `sqlite_master`/`PRAGMA` and validated against a hardcoded allowlist, or are literal SQL expressions (`"0.0"`, `"'EUR'"`).

### Legacy schema compatibility

The extractor handles two generations of schema transparently:

| Feature | Legacy | Current |
|---|---|---|
| Snapshot table name | `snapshots` | `portfolio_snapshots` |
| Snapshot value column | `total_value_eur` | `total_market_value_eur` |
| Quantity location | `assets.quantity` | `asset_snapshots.quantity` |
| Native price/currency | absent (falls back to `0.0` / `'EUR'`) | `asset_snapshots.native_price/currency` |

---

## Usage pattern

```python
from infra.database.connection import get_db_context
from infra.database.schema import initialize_database
from infra.database.finance_sql_extraction import FinanceSQLExtractor

# Bootstrap (idempotent — safe to call on every startup)
with get_db_context() as conn:
    initialize_database(conn)

# Write (within a transaction)
with get_db_context() as conn:
    conn.execute("INSERT INTO assets (...) VALUES (...)")

# Read historical data
extractor = FinanceSQLExtractor()
asset_history     = extractor.fetch_asset_history()
portfolio_history = extractor.fetch_portfolio_history()
```
