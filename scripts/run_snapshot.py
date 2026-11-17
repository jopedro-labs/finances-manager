"""
Persists a new portfolio snapshot to SQLite and backs up the database to Google Drive.

Usage:
    python scripts/run_snapshot.py <path_to_json_file>

The JSON file must contain a complete snapshot object matching the format produced
by the extractor agent. Pass a file path to avoid shell escaping issues.
The temp file is deleted after successful processing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR: Path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "core"))

from core_lib.logger import logger
from dotenv import load_dotenv

from config import get_settings
from infra.database.connection import get_db_context
from infra.database.schema import initialize_database

load_dotenv()


def _get_asset_id(cursor: Any, yahoo_ticker: str, isin: str | None) -> int | None:
    if isin:
        cursor.execute("SELECT id FROM assets WHERE isin = ?", (isin,))
        row: sqlite3.Row | None = cursor.fetchone()
        if row:
            return int(row["id"])
    cursor.execute("SELECT id FROM assets WHERE yahoo_ticker = ?", (yahoo_ticker,))
    row: sqlite3.Row | None = cursor.fetchone()
    return int(row["id"]) if row else None


def _sync_assets_from_portfolio(cursor: Any, db_path: Path) -> None:
    """Upserts assets from portfolio.json into the assets table.

    Runs before every snapshot so new assets added to portfolio.json are
    automatically available without manual DB intervention.
    """
    portfolio_path: Path = db_path.parent / "portfolio.json"
    if not portfolio_path.exists():
        return

    with open(portfolio_path, encoding="utf-8") as f:
        portfolio: dict[str, Any] = json.load(f)

    item: dict[str, Any]
    for item in portfolio.get("assets", []):
        isin: str | None = item.get("isin")
        yahoo_ticker: str = str(item.get("yahoo_ticker", ""))
        name: str = str(item.get("name", yahoo_ticker))
        asset_type: str = str(item.get("asset_type", "STOCK")).upper()
        native_currency: str = str(item.get("native_currency", "EUR")).upper()
        quantity: float = float(item.get("quantity", 0.0))
        avg_price: float = float(item.get("average_buy_price", 0.0))
        xtb_name: str | None = item.get("xtb_name")
        xtb_ticker: str | None = item.get("xtb_ticker")
        just_etf_ticker: str | None = item.get("just_etf_ticker")

        cursor.execute(
            """
            INSERT INTO assets (
                isin, name, yahoo_ticker, quantity, average_buy_price,
                asset_type, xtb_name, xtb_ticker, just_etf_ticker, native_currency
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(isin) DO UPDATE SET
                name              = excluded.name,
                yahoo_ticker      = excluded.yahoo_ticker,
                quantity          = excluded.quantity,
                average_buy_price = excluded.average_buy_price,
                asset_type        = excluded.asset_type,
                xtb_name          = excluded.xtb_name,
                xtb_ticker        = excluded.xtb_ticker,
                just_etf_ticker   = excluded.just_etf_ticker,
                native_currency   = excluded.native_currency
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


def save_snapshot(snapshot: dict[str, Any]) -> None:
    """Persists a new portfolio snapshot directly to SQLite.

    Resolves each asset by ISIN (primary) or yahoo_ticker (fallback) against the
    assets table. Skips any asset not found with a warning. The snapshot date
    is deduplicated — an existing entry for the same date is replaced.

    Args:
        snapshot: A dictionary with the structured portfolio snapshot payload
            produced by the extractor agent.

    Raises:
        SystemExit: If the database write fails irrecoverably or data is invalid.
    """
    settings: Any = get_settings()
    db_path: Path = settings.finance_db_file

    snapshot_date: str = str(snapshot.get("date", ""))
    timestamp: str = str(snapshot.get("timestamp", f"{snapshot_date}T00:00:00Z"))
    total_invested: float = float(snapshot.get("total_invested_eur", 0.0))
    total_market_value: float = float(snapshot.get("total_market_value_eur", 0.0))

    breakdown: dict[str, Any] = snapshot.get("breakdown", {})
    stocks_eur: float = float(breakdown.get("stocks_eur", 0.0))

    # Guard clause: Abort snapshot if essential portfolio data or stocks are missing/zero
    if total_market_value <= 0.0 or stocks_eur <= 0.0:
        logger.error(
            f"[snapshot] Aborting snapshot: Invalid or missing portfolio data detected "
            f"(total_market_value_eur: €{total_market_value}, stocks_eur: €{stocks_eur}). "
            "Ensure the XTB screenshot was successfully processed."
        )
        sys.exit(1)

    unrealized_pnl: float = float(
        snapshot.get("unrealized_pnl_eur", total_market_value - total_invested)
    )
    unrealized_pct: float = float(
        snapshot.get(
            "unrealized_pnl_pct",
            (unrealized_pnl / total_invested * 100.0) if total_invested > 0 else 0.0,
        )
    )
    currencies_json: str = json.dumps(snapshot.get("currencies_rate", {}))
    breakdown_json: str = json.dumps(breakdown)

    try:
        with get_db_context(str(db_path)) as conn:
            initialize_database(conn)
            cursor: Any = conn.cursor()

            # Auto-sync assets from portfolio.json — new assets are inserted automatically
            _sync_assets_from_portfolio(cursor, db_path)

            # Idempotent upsert — replace snapshot for this date if it already exists
            cursor.execute(
                "DELETE FROM portfolio_snapshots WHERE timestamp LIKE ?",
                (f"{snapshot_date}%",),
            )

            cursor.execute(
                """
                INSERT INTO portfolio_snapshots (
                    timestamp, total_invested_eur, total_market_value_eur,
                    unrealized_pnl_eur, unrealized_pnl_pct,
                    currencies_rate_json, breakdown_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    total_invested,
                    total_market_value,
                    unrealized_pnl,
                    unrealized_pct,
                    currencies_json,
                    breakdown_json,
                ),
            )
            snapshot_id: int = int(cursor.lastrowid)

            assets_raw: list[dict[str, Any]] = (
                snapshot.get("holdings") or snapshot.get("assets") or snapshot.get("asset") or []
            )

            item: dict[str, Any]
            for item in assets_raw:
                yahoo_ticker: str = str(item.get("yahoo_ticker") or item.get("ticker", ""))
                isin: str | None = item.get("isin")
                native_currency: str = str(item.get("native_currency", "EUR")).upper()
                currency_suffix: str = native_currency.lower()

                asset_id: int | None = _get_asset_id(cursor, yahoo_ticker, isin)
                if asset_id is None:
                    logger.warning(
                        f"[snapshot] Asset '{yahoo_ticker}' not found in assets table — skipping."
                    )
                    continue

                quantity: float = float(item.get("quantity", 0.0))
                total_cost_eur: float = float(item.get("total_cost_eur", 0.0))
                market_value_eur: float = float(item.get("market_value_eur", 0.0))
                native_price: float = float(
                    item.get(f"market_price_{currency_suffix}")
                    or item.get("market_price", 0.0)
                    or 0.0
                )

                cursor.execute(
                    """
                    INSERT OR IGNORE INTO asset_snapshots (
                        snapshot_id, asset_id, quantity, invested_eur,
                        native_price, native_currency, value_eur
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        asset_id,
                        quantity,
                        total_cost_eur,
                        native_price,
                        native_currency,
                        market_value_eur,
                    ),
                )

        logger.success(
            f"[snapshot] Snapshot for {snapshot_date} saved to SQLite "
            f"(total: €{total_market_value}, P&L: €{unrealized_pnl:+.2f})."
        )

    except Exception as error:
        logger.error(f"[snapshot] Failed to save snapshot: {error}")
        sys.exit(1)


def push_to_gdrive() -> None:
    """Backs up the SQLite database to Google Drive.

    Uploads the current local database directly to Google Drive, overwriting
    the existing 'finances.db' file to maintain a single up-to-date cloud version.
    """
    try:
        from core_lib.gdrive import GDriveService

        settings: Any = get_settings()
        db_path: Path = settings.finance_db_file

        if not db_path.exists():
            logger.warning("[snapshot] Database file not found — skipping GDrive backup.")
            return

        drive: Any = GDriveService(
            credentials_path="secrets/credentials.json",
            token_path="secrets/token.json",
            folder_id=settings.gdrive_snapshots_folder_id,
        )

        file_id: str | None = drive.upload_file(
            file_path=db_path,
            mime_type="application/x-sqlite3",
            overwrite=True,
        )

        if file_id is None:
            logger.warning("[snapshot] Could not back up database to Google Drive.")
            return

        logger.success("[snapshot] Database successfully updated on Google Drive.")

    except Exception as error:
        logger.error(f"[snapshot] Error syncing with Google Drive: {error}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.info("[snapshot] Usage: python scripts/run_snapshot.py <path_to_json_file>")
        sys.exit(1)

    input_path: Path = Path(sys.argv[1])
    if not input_path.exists():
        logger.error(f"[snapshot] File not found — {input_path}")
        sys.exit(1)

    try:
        with open(input_path, encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"[snapshot] Invalid JSON — {e}")
        sys.exit(1)

    save_snapshot(data)
    push_to_gdrive()

    # Delete the ephemeral IPC file after successful processing
    if input_path.name == ".temp_snapshot.json":
        input_path.unlink(missing_ok=True)
