"""
SQL extraction queries for historical portfolio and asset analytics.
Provides immutable data structures and secure, injection-safe SQL query execution
against the portfolio SQLite database. All column references are validated against
explicit allowlists before interpolation into dynamic queries.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from infra.database.connection import get_db_context

_ALLOWED_DATE_COLS: frozenset[str] = frozenset({"date", "timestamp"})
_ALLOWED_TICKER_COLS: frozenset[str] = frozenset({"ticker", "yahoo_ticker"})
_ALLOWED_TYPE_COLS: frozenset[str] = frozenset({"type", "asset_type"})

# Canonical snapshot table name in the current schema.
# Legacy databases may still use 'snapshots' — _get_column_name resolves this at runtime.
_SNAPSHOT_TABLE_CANDIDATES: list[str] = ["portfolio_snapshots", "snapshots"]


@dataclass(frozen=True)
class AssetHistoricalRecord:
    """Immutable historical data point for a specific asset within a portfolio snapshot.

    Attributes:
        snapshot_date: ISO8601 timestamp string of the snapshot.
        asset_ticker: Yahoo Finance ticker symbol for the asset.
        asset_name: Human-readable asset name.
        asset_type: Asset classification ('STOCK' or 'ETF').
        quantity: Units held at the moment of the snapshot.
        value_eur: Total market value in EUR at snapshot time.
        native_price: Asset price in its native currency at snapshot time.
        native_currency: ISO 4217 currency code (e.g. 'EUR', 'USD').
    """

    snapshot_date: str
    asset_ticker: str
    asset_name: str
    asset_type: str
    quantity: float
    value_eur: float
    native_price: float = 0.0
    native_currency: str = "EUR"


@dataclass(frozen=True)
class PortfolioHistoricalRecord:
    """Immutable historical data point for total portfolio valuation at a snapshot.

    Attributes:
        snapshot_date: ISO8601 timestamp string of the snapshot.
        total_value_eur: Total portfolio market value in EUR at snapshot time.
    """

    snapshot_date: str
    total_value_eur: float


class FinanceSQLExtractor:
    """Extracts historical performance data from the portfolio SQLite database.

    All dynamic SQL is constructed using column names validated against explicit
    allowlists to prevent SQL injection. Legacy schema variations are handled
    transparently via PRAGMA-based introspection at query time.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        """Initialises the extractor with a target SQLite database path.

        Args:
            db_path: Path to the SQLite database file. If None, resolves from
                application settings at query time via get_db_context default.
        """
        self._db_path: Path | None = Path(db_path) if db_path is not None else None

    @property
    def db_path(self) -> Path | None:
        """The configured database path, or None if using the settings default."""
        return self._db_path

    @staticmethod
    def _get_column_name(cursor: sqlite3.Cursor, table: str, candidates: list[str]) -> str:
        """Resolves the first existing column name from a list of candidates.

        Args:
            cursor: Active database cursor.
            table: Table name to inspect via PRAGMA table_info.
            candidates: Ordered list of candidate column names to check.

        Returns:
            The first candidate column name that exists in the table.

        Raises:
            ValueError: If none of the candidate columns exist in the table.
        """
        cursor.execute(f"PRAGMA table_info({table});")  # nosec B608
        existing_cols: set[str] = {row[1] for row in cursor.fetchall()}
        for candidate in candidates:
            if candidate in existing_cols:
                return candidate
        raise ValueError(f"None of the candidate columns {candidates} exist in table '{table}'.")

    @staticmethod
    def _get_table_name(cursor: sqlite3.Cursor, candidates: list[str]) -> str:
        """Resolves the first existing table name from a list of candidates.

        Args:
            cursor: Active database cursor.
            candidates: Ordered list of candidate table names to check.

        Returns:
            The first candidate table name that exists in the database.

        Raises:
            ValueError: If none of the candidate tables exist in the database.
        """
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables: set[str] = {row[0] for row in cursor.fetchall()}
        for candidate in candidates:
            if candidate in existing_tables:
                return candidate
        raise ValueError(f"None of the candidate tables {candidates} exist in the database.")

    @staticmethod
    def _safe_col(value: str, allowed: frozenset[str]) -> str:
        """Validates a column name against an explicit allowlist to prevent SQL injection.

        Args:
            value: Column name to validate.
            allowed: Frozenset of permitted column names.

        Returns:
            The validated column name string.

        Raises:
            ValueError: If the value is not in the allowed set.
        """
        if value not in allowed:
            raise ValueError(f"Column name '{value}' is not in the allowed list: {allowed}.")
        return value

    @staticmethod
    def _resolve_quantity_col(cursor: sqlite3.Cursor) -> str:
        """Resolves the SELECT expression for quantity based on schema version.

        In the current schema, quantity is stored in asset_snapshots (immutable
        at snapshot time). Legacy schemas stored it only in the assets table.

        Args:
            cursor: Active database cursor used to inspect asset_snapshots columns.

        Returns:
            SQL expression string referencing the correct quantity column.
        """
        cursor.execute("PRAGMA table_info(asset_snapshots);")  # nosec B608
        ast_cols: set[str] = {row[1] for row in cursor.fetchall()}
        return "ast.quantity" if "quantity" in ast_cols else "a.quantity"

    @staticmethod
    def _resolve_native_cols(cursor: sqlite3.Cursor) -> tuple[str, str]:
        """Resolves SELECT expressions for native_price and native_currency.

        Falls back to literal defaults (0.0 / 'EUR') for legacy schemas that
        predate the introduction of native currency tracking in asset_snapshots.

        Args:
            cursor: Active database cursor used to inspect asset_snapshots columns.

        Returns:
            Tuple of (price_expr, currency_expr) SQL expression strings.
        """
        cursor.execute("PRAGMA table_info(asset_snapshots);")  # nosec B608
        ast_cols: set[str] = {row[1] for row in cursor.fetchall()}
        price_expr = "ast.native_price" if "native_price" in ast_cols else "0.0"
        currency_expr = "ast.native_currency" if "native_currency" in ast_cols else "'EUR'"
        return price_expr, currency_expr

    def fetch_asset_history(self) -> list[AssetHistoricalRecord]:
        """Fetches all historical asset snapshot records joined with asset metadata.

        Resolves schema variations at runtime (legacy column names, legacy table
        names) to ensure compatibility with both current and pre-migration databases.
        Returns an empty list gracefully if the database does not exist or has not
        yet been initialised (tables missing).

        Returns:
            List of AssetHistoricalRecord instances ordered by date ascending,
            then by ticker ascending. Returns an empty list if the database does
            not exist, is uninitialised, or contains no asset snapshot records.
        """
        if self._db_path is not None and not self._db_path.exists():
            return []

        try:
            records: list[AssetHistoricalRecord] = []
            with get_db_context(self._db_path) as conn:
                cursor: sqlite3.Cursor = conn.cursor()

                snapshot_table: str = self._get_table_name(cursor, _SNAPSHOT_TABLE_CANDIDATES)
                date_col: str = self._safe_col(
                    self._get_column_name(cursor, snapshot_table, ["date", "timestamp"]),
                    _ALLOWED_DATE_COLS,
                )
                ticker_col: str = self._safe_col(
                    self._get_column_name(cursor, "assets", ["ticker", "yahoo_ticker"]),
                    _ALLOWED_TICKER_COLS,
                )
                type_col: str = self._safe_col(
                    self._get_column_name(cursor, "assets", ["type", "asset_type"]),
                    _ALLOWED_TYPE_COLS,
                )
                qty_col: str = self._resolve_quantity_col(cursor)
                native_price_expr, native_currency_expr = self._resolve_native_cols(cursor)

                query: str = (
                    f"SELECT s.{date_col} AS snapshot_date, "  # nosec B608
                    f"a.{ticker_col} AS asset_ticker, "
                    f"a.name AS asset_name, "
                    f"a.{type_col} AS asset_type, "
                    f"{qty_col} AS quantity, "
                    f"ast.value_eur AS value_eur, "
                    f"{native_price_expr} AS native_price, "
                    f"{native_currency_expr} AS native_currency "
                    f"FROM {snapshot_table} s "
                    f"JOIN asset_snapshots ast ON ast.snapshot_id = s.id "
                    f"JOIN assets a ON ast.asset_id = a.id "
                    f"ORDER BY s.{date_col} ASC, a.{ticker_col} ASC;"
                )
                cursor.execute(query)
                for row in cursor.fetchall():
                    records.append(
                        AssetHistoricalRecord(
                            snapshot_date=str(row["snapshot_date"]),
                            asset_ticker=str(row["asset_ticker"]),
                            asset_name=str(row["asset_name"]),
                            asset_type=str(row["asset_type"]),
                            quantity=float(row["quantity"]),
                            value_eur=float(row["value_eur"]),
                            native_price=float(row["native_price"]),
                            native_currency=str(row["native_currency"]),
                        )
                    )
            return records
        except ValueError:
            return []

    def fetch_portfolio_history(self) -> list[PortfolioHistoricalRecord]:
        """Fetches all global portfolio valuation snapshot records.

        Filters to only include snapshots that are either marked as baseline
        or contain a complete set of asset entries (one per active asset),
        ensuring partial or corrupt snapshots are excluded from history.
        Returns an empty list gracefully if the database does not exist or has not
        yet been initialised (tables missing).

        Returns:
            List of PortfolioHistoricalRecord instances ordered by date ascending.
            Returns an empty list if the database does not exist, is uninitialised,
            or contains no qualifying snapshot records.
        """
        if self._db_path is not None and not self._db_path.exists():
            return []

        try:
            records: list[PortfolioHistoricalRecord] = []
            with get_db_context(self._db_path) as conn:
                cursor: sqlite3.Cursor = conn.cursor()

                snapshot_table: str = self._get_table_name(cursor, _SNAPSHOT_TABLE_CANDIDATES)
                date_col: str = self._safe_col(
                    self._get_column_name(cursor, snapshot_table, ["date", "timestamp"]),
                    _ALLOWED_DATE_COLS,
                )

                cursor.execute(f"PRAGMA table_info({snapshot_table})")  # nosec B608
                snap_cols: set[str] = {row["name"] for row in cursor.fetchall()}
                cursor.execute("PRAGMA table_info(assets)")
                asset_cols: set[str] = {row["name"] for row in cursor.fetchall()}

                has_baseline: bool = "is_baseline" in snap_cols
                has_quantity: bool = "quantity" in asset_cols

                baseline_clause: str = "COALESCE(s.is_baseline, 0) = 1" if has_baseline else "0 = 1"
                active_filter: str = " AND quantity > 0" if has_quantity else ""

                total_value_col: str = (
                    "total_market_value_eur"
                    if "total_market_value_eur" in snap_cols
                    else "total_value_eur"
                )

                query: str = (
                    f"SELECT s.{date_col} AS snapshot_date, "  # nosec B608
                    f"s.{total_value_col} AS total_value_eur "
                    f"FROM {snapshot_table} s "
                    f"WHERE s.{total_value_col} > 0 "
                    f"AND ({baseline_clause} OR ("
                    f"  SELECT COUNT(*) FROM asset_snapshots sa "
                    f"  WHERE sa.snapshot_id = s.id"
                    f") = ("
                    f"  SELECT COUNT(*) FROM assets WHERE 1=1{active_filter})) "
                    f"ORDER BY s.{date_col} ASC;"
                )
                cursor.execute(query)
                for row in cursor.fetchall():
                    records.append(
                        PortfolioHistoricalRecord(
                            snapshot_date=str(row["snapshot_date"]),
                            total_value_eur=float(row["total_value_eur"]),
                        )
                    )
            return records
        except ValueError:
            return []
