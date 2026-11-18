"""
Database schema definition and initialization DDL statements.
Manages relational tables, performance indexes, and idempotent migration execution for SQLite.
"""

from __future__ import annotations

import sqlite3

from core_lib.logger import logger

_ALLOWED_MIGRATION_TABLES: frozenset[str] = frozenset(
    {"stock_fundamental_history", "etf_fundamental_history"}
)
_ALLOWED_MIGRATION_COLUMNS: frozenset[str] = frozenset({"quality_tier", "quality_score"})
_ALLOWED_MIGRATION_COL_TYPES: frozenset[str] = frozenset({"TEXT", "INTEGER", "REAL"})

CREATE_ASSETS_TABLE_SQL: str = """
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    isin TEXT UNIQUE,
    name TEXT NOT NULL,
    yahoo_ticker TEXT NOT NULL,
    quantity REAL NOT NULL,
    average_buy_price REAL NOT NULL,
    asset_type TEXT NOT NULL CHECK (UPPER(asset_type) IN ('STOCK', 'ETF')),
    xtb_name TEXT,
    xtb_ticker TEXT,
    just_etf_ticker TEXT,
    native_currency TEXT NOT NULL DEFAULT 'EUR',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# unrealized_pnl_eur and unrealized_pnl_pct are stored redundantly for read performance.
# Source of truth: total_market_value_eur - total_invested_eur.
# Writers must always compute these from the sovereign values before inserting.
# currencies_rate_json stores a dictionary of currency exchange rates.
# breakdown_json stores the portfolio allocation breakdown dictionary.
CREATE_PORTFOLIO_SNAPSHOTS_TABLE_SQL: str = """
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL UNIQUE,
    total_invested_eur REAL NOT NULL,
    total_market_value_eur REAL NOT NULL,
    unrealized_pnl_eur REAL NOT NULL,
    unrealized_pnl_pct REAL NOT NULL,
    currencies_rate_json TEXT,
    breakdown_json TEXT,
    is_baseline INTEGER NOT NULL DEFAULT 0 CHECK (is_baseline IN (0, 1))
);
"""

# quantity and invested_eur are captured at the exact moment of the snapshot to ensure
# absolute historical immutability.
# native_price, native_currency, and value_eur record original pricing and EUR conversion.
CREATE_ASSET_SNAPSHOTS_TABLE_SQL: str = """
CREATE TABLE IF NOT EXISTS asset_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL,
    asset_id INTEGER NOT NULL,
    quantity REAL NOT NULL,
    invested_eur REAL NOT NULL,
    native_price REAL NOT NULL,
    native_currency TEXT NOT NULL,
    value_eur REAL NOT NULL,
    FOREIGN KEY (snapshot_id) REFERENCES portfolio_snapshots (id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES assets (id) ON DELETE CASCADE,
    UNIQUE (snapshot_id, asset_id)
);
"""

# stock_fundamental_history stores time-series fundamental metrics for stock assets,
# enabling historical tracking of valuation ratios, profitability, and quality scores.
CREATE_STOCK_FUNDAMENTALS_TABLE_SQL: str = """
CREATE TABLE IF NOT EXISTS stock_fundamental_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    fetched_at TEXT NOT NULL CHECK (fetched_at LIKE '____-__-__ %' OR fetched_at LIKE '____-__-__T%'),
    market_cap REAL,
    pe_ratio REAL,
    forward_pe REAL,
    price_to_book REAL,
    peg_ratio REAL,
    dividend_yield_pct REAL,
    return_on_equity_pct REAL,
    total_debt_to_equity REAL,
    free_cashflow REAL,
    beta REAL,
    eps_trailing_ttm REAL,
    fifty_two_week_high REAL,
    fifty_two_week_low REAL,
    sector TEXT,
    industry TEXT,
    quality_tier TEXT,
    quality_score INTEGER,
    FOREIGN KEY (asset_id) REFERENCES assets (id) ON DELETE CASCADE
);
"""

# etf_fundamental_history stores time-series fundamental metrics and composition snapshots
# for ETF assets, tracking TER, fund size, volatility, holdings count, and breakdowns.
CREATE_ETF_FUNDAMENTALS_TABLE_SQL: str = """
CREATE TABLE IF NOT EXISTS etf_fundamental_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    fetched_at TEXT NOT NULL CHECK (fetched_at LIKE '____-__-__ %' OR fetched_at LIKE '____-__-__T%'),
    ter_pct REAL,
    fund_size_eur_m REAL,
    holdings_count INTEGER,
    volatility_1y_pct REAL,
    holdings_json TEXT,
    sector_breakdown_json TEXT,
    country_breakdown_json TEXT,
    quality_tier TEXT,
    quality_score INTEGER,
    FOREIGN KEY (asset_id) REFERENCES assets (id) ON DELETE CASCADE
);
"""

# Active/latest fundamental cache table (stores the single most recent fetch per asset,
# whereas stock_fundamental_history and etf_fundamental_history preserve time-series data).
CREATE_ASSET_FUNDAMENTALS_TABLE_SQL: str = """
CREATE TABLE IF NOT EXISTS asset_fundamentals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL UNIQUE,
    asset_type TEXT NOT NULL CHECK (UPPER(asset_type) IN ('STOCK', 'ETF')),
    fetched_at TEXT NOT NULL CHECK (fetched_at LIKE '____-__-__ %' OR fetched_at LIKE '____-__-__T%'),
    details_json TEXT NOT NULL,
    quality_tier TEXT,
    quality_score INTEGER,
    FOREIGN KEY (asset_id) REFERENCES assets (id) ON DELETE CASCADE
);
"""

# unrealized_pnl_eur is stored redundantly for read performance.
# Source of truth: total_value_eur - total_invested_eur.
# Writers must always compute these from the sovereign values before inserting.
# opportunities stores the global header metadata for each opportunity evaluation run,
# tracking timestamp, portfolio valuation, invested capital, PnL, and AI enablement status.
CREATE_OPPORTUNITIES_TABLE_SQL: str = """
CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL UNIQUE,
    total_invested_eur REAL NOT NULL DEFAULT 0.0,
    total_value_eur REAL NOT NULL,
    unrealized_pnl_eur REAL NOT NULL DEFAULT 0.0,
    has_ai INTEGER NOT NULL CHECK (has_ai IN (0, 1))
);
"""

# opportunity_asset_metrics stores asset-level ranking, scores, fundamental ratios,
# and AI recommendations for each execution run in the opportunities pipeline.
CREATE_OPPORTUNITY_ASSET_METRICS_TABLE_SQL: str = """
CREATE TABLE IF NOT EXISTS opportunity_asset_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    rank INTEGER NOT NULL,
    price_eur REAL NOT NULL,
    current_allocation_pct REAL NOT NULL,
    target_allocation_pct REAL NOT NULL,
    dip_score REAL NOT NULL,
    cost_score REAL NOT NULL,
    gap_score REAL NOT NULL,
    quant_score REAL NOT NULL,
    ai_action TEXT,
    ai_urgency TEXT,
    ai_confidence_pct REAL,
    risk_score INTEGER,
    valuation_score INTEGER,
    forward_pe REAL,
    trailing_pe REAL,
    peg_ratio REAL,
    price_to_book REAL,
    dividend_yield_pct REAL,
    ter REAL,
    advisory_json TEXT,
    FOREIGN KEY (opportunity_id) REFERENCES opportunities (id) ON DELETE CASCADE,
    UNIQUE (opportunity_id, symbol)
);
"""

# Performance indexes optimizing relational joins, historical time-series lookups,
# asset symbol resolution, and opportunity ranking queries.
CREATE_INDEXES_SQL: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_asset_snapshots_snapshot_id ON asset_snapshots (snapshot_id);",
    "CREATE INDEX IF NOT EXISTS idx_asset_snapshots_asset_id ON asset_snapshots (asset_id);",
    "CREATE INDEX IF NOT EXISTS idx_opportunity_metrics_opp_id ON opportunity_asset_metrics (opportunity_id);",
    "CREATE INDEX IF NOT EXISTS idx_opportunity_metrics_rank ON opportunity_asset_metrics (opportunity_id, rank);",
    "CREATE INDEX IF NOT EXISTS idx_stock_fundamentals_lookup ON stock_fundamental_history (asset_id, fetched_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_etf_fundamentals_lookup ON etf_fundamental_history (asset_id, fetched_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_assets_yahoo_ticker ON assets (yahoo_ticker);",
]


def create_tables(conn: sqlite3.Connection) -> None:
    """Executes DDL statements to create all required database relational tables,
    enforces foreign key constraints, and builds performance indexes idempotently.

    Args:
        conn: Active sqlite3.Connection instance.

    Raises:
        sqlite3.Error: If any DDL execution or index creation fails.
    """
    cursor: sqlite3.Cursor = conn.cursor()
    try:
        # Enforce foreign key constraints at the connection level for SQLite
        cursor.execute("PRAGMA foreign_keys = ON;")

        # Create core domain tables in topological dependency order
        cursor.execute(CREATE_ASSETS_TABLE_SQL)
        cursor.execute(CREATE_PORTFOLIO_SNAPSHOTS_TABLE_SQL)
        cursor.execute(CREATE_ASSET_SNAPSHOTS_TABLE_SQL)
        cursor.execute(CREATE_STOCK_FUNDAMENTALS_TABLE_SQL)
        cursor.execute(CREATE_ETF_FUNDAMENTALS_TABLE_SQL)
        cursor.execute(CREATE_OPPORTUNITIES_TABLE_SQL)
        cursor.execute(CREATE_OPPORTUNITY_ASSET_METRICS_TABLE_SQL)
        cursor.execute(CREATE_ASSET_FUNDAMENTALS_TABLE_SQL)

        # Create performance optimization indexes
        for index_sql in CREATE_INDEXES_SQL:
            cursor.execute(index_sql)

        conn.commit()
        logger.success(
            "[schema] All database tables and performance indexes were successfully initialized."
        )
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"[schema] Failed to initialize database schema: {e}")
        raise


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Applies safe, idempotent schema migrations with precise error handling,
    transaction safety, and explicit allowlist validations.

    Args:
        conn: Active sqlite3.Connection instance.

    Raises:
        ValueError: If an unauthorized table or column migration is attempted.
        sqlite3.Error: If the migration execution fails unexpectedly.
    """
    cursor: sqlite3.Cursor = conn.cursor()

    try:
        # Legacy migration support for existing databases lacking 'advisory_json' column
        try:
            cursor.execute("ALTER TABLE opportunity_asset_metrics ADD COLUMN advisory_json TEXT;")
            logger.success(
                "[schema] Successfully added legacy column 'advisory_json' to table 'opportunity_asset_metrics'."
            )
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        # Legacy migration support for existing databases lacking 'is_baseline' column
        # NOTE: SQLite ALTER TABLE ADD COLUMN does not support CHECK constraints —
        # legacy databases will have this column without CHECK (is_baseline IN (0, 1)).
        try:
            cursor.execute(
                "ALTER TABLE portfolio_snapshots ADD COLUMN is_baseline INTEGER NOT NULL DEFAULT 0;"
            )
            logger.success(
                "[schema] Successfully added legacy column 'is_baseline' to table 'portfolio_snapshots'."
            )
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        # Idempotent schema enhancements for fundamental history tables
        for table in ("stock_fundamental_history", "etf_fundamental_history"):
            for column, col_type in [
                ("quality_tier", "TEXT"),
                ("quality_score", "INTEGER"),
            ]:
                if (
                    table not in _ALLOWED_MIGRATION_TABLES
                    or column not in _ALLOWED_MIGRATION_COLUMNS
                ):
                    raise ValueError(f"[schema] Disallowed migration target: {table}.{column}")
                if col_type not in _ALLOWED_MIGRATION_COL_TYPES:
                    raise ValueError(f"[schema] Disallowed column type: {col_type}")

                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type};")  # nosec B608
                    logger.success(
                        f"[schema] Successfully added column '{column}' to table '{table}'."
                    )
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise

        conn.commit()
        logger.success(
            "[schema] All database schema migrations were successfully verified and applied."
        )
    except Exception as e:
        conn.rollback()
        logger.error(f"[schema] Failed to apply database migrations: {e}")
        raise


def initialize_database(conn: sqlite3.Connection) -> None:
    """Initializes the SQLite database by orchestrating schema creation,
    performance index setup, and applying safe incremental migrations.

    Args:
        conn: Active sqlite3.Connection instance.

    Raises:
        sqlite3.Error: If database initialization or migration execution fails.
    """
    try:
        logger.info("[schema] Initializing database schema and performance indexes...")
        create_tables(conn)

        logger.info("[schema] Verifying and applying pending database schema migrations...")
        apply_migrations(conn)

        logger.success("[schema] Database initialization completed successfully.")
    except Exception as e:
        logger.error(f"[schema] Critical error during database initialization: {e}")
        raise
