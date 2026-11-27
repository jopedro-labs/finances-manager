"""Script for migrating and reconciling portfolio seed JSON data into SQLite.

Reads portfolio.json and upserts all assets into the SQLite assets table,
ensuring database state is aligned without duplicating entries.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure root directory is in pythonpath
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core_lib.logger import logger  # noqa: E402

from config import DATA_DIR, get_settings  # noqa: E402
from infra.database.connection import get_db_context  # noqa: E402
from infra.database.schema import initialize_database  # noqa: E402


def migrate_portfolio_to_sqlite() -> None:
    """Reconciles and upserts assets from data/portfolio.json into the SQLite database."""
    settings = get_settings()
    db_path = settings.finance_db_file
    portfolio_file = DATA_DIR / "portfolio.json"

    if not portfolio_file.exists():
        logger.error(f"[migrate] Portfolio file not found at '{portfolio_file}'.")
        sys.exit(1)

    logger.section("[migrate] Reconciling Portfolio JSON Seed with SQLite Database")

    with open(portfolio_file, encoding="utf-8") as f:
        data = json.load(f)

    assets_data = data.get("assets", [])
    if not assets_data:
        logger.warning("[migrate] No assets found in portfolio.json to migrate.")
        return

    with get_db_context(str(db_path)) as conn:
        initialize_database(conn)
        cur = conn.cursor()

        migrated_count = 0
        for item in assets_data:
            isin = item.get("isin")
            name = item.get("name")
            yahoo_ticker = item.get("yahoo_ticker", "")
            asset_type = str(item.get("asset_type", "STOCK")).upper()
            native_currency = str(item.get("native_currency", "EUR")).upper()
            quantity = float(item.get("quantity", 0.0))
            avg_price = float(item.get("average_buy_price", 0.0))
            xtb_name = item.get("xtb_name")
            xtb_ticker = item.get("xtb_ticker")
            just_etf_ticker = item.get("just_etf_ticker")

            cur.execute(
                """
                INSERT INTO assets (
                    isin, name, yahoo_ticker, quantity, average_buy_price,
                    asset_type, xtb_name, xtb_ticker, just_etf_ticker, native_currency
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(isin) DO UPDATE SET
                    name = excluded.name,
                    yahoo_ticker = excluded.yahoo_ticker,
                    asset_type = excluded.asset_type,
                    native_currency = excluded.native_currency;
                """,
                (
                    isin,
                    name,
                    yahoo_ticker,
                    quantity,
                    avg_price,
                    asset_type,
                    xtb_name,
                    xtb_ticker,
                    just_etf_ticker,
                    native_currency,
                ),
            )
            migrated_count += 1

    logger.success(
        f"[migrate] Successfully reconciled {migrated_count} assets into SQLite ('{db_path}')."
    )


if __name__ == "__main__":
    migrate_portfolio_to_sqlite()
