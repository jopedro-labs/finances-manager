"""
Database infrastructure package.
Exposes connection management, schema initialization, and SQL data extraction utilities.
"""

from __future__ import annotations

from infra.database.connection import DEFAULT_DB_PATH, get_connection, get_db_context
from infra.database.finance_sql_extraction import (
    AssetHistoricalRecord,
    FinanceSQLExtractor,
    PortfolioHistoricalRecord,
)
from infra.database.schema import apply_migrations, create_tables, initialize_database

__all__ = [
    "DEFAULT_DB_PATH",
    "get_connection",
    "get_db_context",
    "initialize_database",
    "create_tables",
    "apply_migrations",
    "FinanceSQLExtractor",
    "AssetHistoricalRecord",
    "PortfolioHistoricalRecord",
]
