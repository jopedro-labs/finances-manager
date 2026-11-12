"""Repository protocols and storage implementations (JSON, SQLite, and Parquet) for
portfolio configuration, historical snapshots, and ETF/stock cache data.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from config import (
    DATA_DIR,
    ETF_CACHE_FILE,
    get_settings,
)
from infra.database.connection import DEFAULT_DB_PATH, get_db_context
from core.exceptions import StorageReadError, StorageWriteError
from core.models import Asset, PortfolioSnapshot, ETFDetails, StockDetails, AssetSnapshot
from infra.database.schema import initialize_database
from infra.logger import logger


class PortfolioRepository(Protocol):
    """Protocol defining core operations for reading and writing portfolio configuration."""

    def load_assets(self) -> list[Asset]:
        """Loads all configured assets from storage."""
        ...


class HistoryRepository(Protocol):
    """Protocol defining operations for portfolio history persistence."""

    def load_history(self) -> list[PortfolioSnapshot]:
        """Loads all recorded portfolio snapshots from storage."""
        ...

    def save_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        """Saves a new portfolio snapshot to storage."""
        ...


class ETFCacheRepository(Protocol):
    """Protocol defining operations for caching ETF metadata."""

    def get_etf_details(self, isin: str) -> ETFDetails | None:
        """Retrieves cached ETF details for a given ISIN if available and valid."""
        ...

    def save_etf_details(self, isin: str, details: ETFDetails) -> None:
        """Saves or updates ETF details in the cache."""
        ...


class SqlitePortfolioRepository:
    """SQLite database-backed implementation of PortfolioRepository."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        """Initializes the SQLite portfolio repository with a target database path.

        Args:
            db_path: Path to the SQLite database.
        """
        self.db_path: Path = Path(db_path)

    def load_assets(self) -> list[Asset]:
        """Loads all active portfolio assets with quantity > 0 from the SQLite database.

        Returns:
            A list of Asset instances parsed from database rows.
        """
        if not self.db_path.exists():
            return []

        try:
            with get_db_context(str(self.db_path)) as conn:
                initialize_database(conn)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT isin, name, yahoo_ticker, quantity, "
                    "average_buy_price, asset_type FROM assets "
                    "WHERE quantity > 0 ORDER BY id ASC"
                )
                rows = cursor.fetchall()
                return [
                    Asset(
                        name=str(row["name"]),
                        isin=str(row["isin"] or ""),
                        yahoo_ticker=str(row["yahoo_ticker"]),
                        quantity=float(row["quantity"]),
                        average_buy_price=float(row["average_buy_price"]),
                        asset_type=str(row["asset_type"]),
                    )
                    for row in rows
                ]
        except Exception as e:
            raise StorageReadError(
                f"[repositories] Failed to read portfolio assets from '{self.db_path}': {e}"
            ) from e

    def get_asset_by_isin(self, isin: str) -> Asset | None:
        """Retrieves a single portfolio asset by its ISIN identifier.

        Args:
            isin: International Securities Identification Number.

        Returns:
            An Asset instance if found, None otherwise.
        """
        if not self.db_path.exists():
            return None

        try:
            with get_db_context(str(self.db_path)) as conn:
                initialize_database(conn)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT isin, name, yahoo_ticker, quantity, "
                    "average_buy_price, asset_type FROM assets WHERE isin = ?",
                    (isin,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return Asset(
                    name=str(row["name"]),
                    isin=str(row["isin"] or ""),
                    yahoo_ticker=str(row["yahoo_ticker"]),
                    quantity=float(row["quantity"]),
                    average_buy_price=float(row["average_buy_price"]),
                    asset_type=str(row["asset_type"]),
                )
        except Exception as e:
            logger.error(f"[repositories] Failed to fetch asset by ISIN '{isin}': {e}")
            return None

    def save_assets(self, assets: list[Asset]) -> None:
        """Saves or updates a list of portfolio assets in the SQLite database.

        Args:
            assets: List of Asset instances to persist.
        """
        try:
            with get_db_context(str(self.db_path)) as conn:
                initialize_database(conn)
                cursor = conn.cursor()
                for asset in assets:
                    cursor.execute(
                        """
                        INSERT INTO assets (
                            isin, name, yahoo_ticker, quantity,
                            average_buy_price, asset_type
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(isin) DO UPDATE SET
                            name=excluded.name,
                            yahoo_ticker=excluded.yahoo_ticker,
                            quantity=excluded.quantity,
                            average_buy_price=excluded.average_buy_price,
                            asset_type=excluded.asset_type;
                        """,
                        (
                            asset.isin if asset.isin else None,
                            asset.name,
                            asset.yahoo_ticker,
                            asset.quantity,
                            asset.average_buy_price,
                            asset.asset_type,
                        ),
                    )
        except Exception as e:
            raise StorageWriteError(
                f"[repositories] Failed to save assets to '{self.db_path}': {e}"
            ) from e


class SqliteHistoryRepository:
    """SQLite database-backed implementation of HistoryRepository."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        """Initializes the SQLite history repository.

        Args:
            db_path: Path to the SQLite database.
        """
        self.db_path: Path = Path(db_path)

    def load_history(self) -> list[PortfolioSnapshot]:
        """Loads all recorded portfolio snapshots and their asset breakdown from SQLite.

        Reads from the current schema table (portfolio_snapshots) with all columns —
        including total_invested_eur, unrealized_pnl_*, and per-asset quantity and
        invested_eur. Non-baseline snapshots only.

        Returns:
            A list of PortfolioSnapshot instances ordered by id ascending.
        """
        if not self.db_path.exists():
            return []

        try:
            with get_db_context(str(self.db_path)) as conn:
                initialize_database(conn)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, timestamp, total_invested_eur, total_market_value_eur, "
                    "unrealized_pnl_eur, unrealized_pnl_pct "
                    "FROM portfolio_snapshots "
                    "WHERE COALESCE(is_baseline, 0) = 0 "
                    "ORDER BY id ASC"
                )
                snapshots_rows = cursor.fetchall()
                snapshots: list[PortfolioSnapshot] = []

                for s_row in snapshots_rows:
                    snapshot_id: int = s_row["id"]
                    cursor.execute(
                        """
                        SELECT a.name, a.isin, a.yahoo_ticker, a.asset_type,
                               a.just_etf_ticker, a.average_buy_price,
                               sa.quantity, sa.invested_eur, sa.native_price,
                               sa.native_currency, sa.value_eur
                        FROM asset_snapshots sa
                        JOIN assets a ON sa.asset_id = a.id
                        WHERE sa.snapshot_id = ?
                        ORDER BY sa.id ASC
                        """,
                        (snapshot_id,),
                    )
                    asset_rows = cursor.fetchall()
                    total_market_value: float = float(s_row["total_market_value_eur"])
                    asset_snaps: list[AssetSnapshot] = []
                    for a_row in asset_rows:
                        quantity: float = float(a_row["quantity"])
                        invested_eur: float = float(a_row["invested_eur"])
                        market_value_eur: float = float(a_row["value_eur"])
                        unrealized_pnl_eur: float = market_value_eur - invested_eur
                        unrealized_pnl_pct: float = (
                            (unrealized_pnl_eur / invested_eur * 100.0)
                            if invested_eur > 0
                            else 0.0
                        )
                        current_allocation_pct: float = (
                            (market_value_eur / total_market_value * 100.0)
                            if total_market_value > 0
                            else 0.0
                        )
                        asset_snaps.append(
                            AssetSnapshot(
                                ticker=str(a_row["yahoo_ticker"]),
                                isin=str(a_row["isin"] or ""),
                                asset_type=str(a_row["asset_type"]).upper(),
                                native_currency=str(a_row["native_currency"]),
                                yahoo_ticker=str(a_row["yahoo_ticker"]),
                                just_etf_ticker=(
                                    str(a_row["just_etf_ticker"])
                                    if a_row["just_etf_ticker"]
                                    else None
                                ),
                                quantity=quantity,
                                average_buy_price=float(a_row["average_buy_price"]),
                                market_price=float(a_row["native_price"]),
                                total_cost_eur=invested_eur,
                                market_value_eur=market_value_eur,
                                unrealized_pnl_eur=unrealized_pnl_eur,
                                unrealized_pnl_pct=unrealized_pnl_pct,
                                target_allocation_pct=0.0,
                                current_allocation_pct=current_allocation_pct,
                            )
                        )

                    snapshots.append(
                        PortfolioSnapshot(
                            date=str(s_row["timestamp"]).split(" ")[0],
                            timestamp=str(s_row["timestamp"]),
                            total_invested_eur=float(s_row["total_invested_eur"]),
                            total_market_value_eur=total_market_value,
                            unrealized_pnl_eur=float(s_row["unrealized_pnl_eur"]),
                            unrealized_pnl_pct=float(s_row["unrealized_pnl_pct"]),
                            holdings=asset_snaps,
                        )
                    )
                return snapshots
        except Exception as e:
            raise StorageReadError(
                f"[repositories] Failed to read history from '{self.db_path}': {e}"
            ) from e

    def save_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        """Persists a new portfolio snapshot and its asset components into SQLite.

        Writes to portfolio_snapshots (current schema) with all required fields
        including total_invested_eur, unrealized_pnl_* and per-asset quantity
        and invested_eur. The asset must already exist in the assets table.

        Args:
            snapshot: PortfolioSnapshot instance to record.

        Raises:
            StorageWriteError: If a referenced ticker is missing from assets or any
                database operation fails.
        """
        try:
            with get_db_context(str(self.db_path)) as conn:
                initialize_database(conn)
                cursor = conn.cursor()

                unrealized_pnl_eur: float = (
                    snapshot.total_market_value_eur - snapshot.total_invested_eur
                )
                unrealized_pnl_pct: float = (
                    (unrealized_pnl_eur / snapshot.total_invested_eur * 100.0)
                    if snapshot.total_invested_eur > 0
                    else 0.0
                )

                cursor.execute(
                    """
                    INSERT INTO portfolio_snapshots (
                        timestamp, total_invested_eur, total_market_value_eur,
                        unrealized_pnl_eur, unrealized_pnl_pct
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot.timestamp,
                        snapshot.total_invested_eur,
                        snapshot.total_market_value_eur,
                        unrealized_pnl_eur,
                        unrealized_pnl_pct,
                    ),
                )
                if cursor.lastrowid is None:
                    raise StorageWriteError("[repositories] Failed to retrieve inserted snapshot ID.")
                snapshot_id: int = cursor.lastrowid

                for asset_snap in snapshot.assets_snapshot:
                    cursor.execute(
                        "SELECT id FROM assets WHERE yahoo_ticker = ?",
                        (asset_snap.yahoo_ticker,),
                    )
                    row = cursor.fetchone()
                    if row:
                        asset_id: int = row["id"]
                    else:
                        raise StorageWriteError(
                            f"[repositories] Ticker '{asset_snap.yahoo_ticker}' not found in "
                            "assets table. Add it to the portfolio before saving snapshots."
                        )

                    cursor.execute(
                        """
                        INSERT INTO asset_snapshots (
                            snapshot_id, asset_id, quantity, invested_eur,
                            native_price, native_currency, value_eur
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            snapshot_id,
                            asset_id,
                            asset_snap.quantity,
                            asset_snap.total_cost_eur,
                            asset_snap.market_price,
                            asset_snap.native_currency,
                            asset_snap.market_value_eur,
                        ),
                    )
        except Exception as e:
            raise StorageWriteError(
                f"[repositories] Failed to save snapshot to '{self.db_path}': {e}"
            ) from e


class ParquetHistoryRepository:
    """Parquet file-backed implementation of HistoryRepository using PyArrow."""

    def __init__(self, file_path: str | Path = DATA_DIR / "history.parquet") -> None:
        """Initializes the Parquet history repository.

        Args:
            file_path: Path to the Parquet file.
        """
        self.file_path: Path = Path(file_path)

    def load_history(self) -> list[PortfolioSnapshot]:
        """Loads all recorded portfolio snapshots from the Parquet file.

        Returns:
            A list of PortfolioSnapshot instances.
        """
        if not self.file_path.exists():
            return []

        try:
            df: pd.DataFrame = pd.read_parquet(str(self.file_path))
            snapshots: list[PortfolioSnapshot] = []
            for _, row in df.iterrows():
                raw_data: dict[str, Any] = json.loads(str(row["snapshot_json"]))
                snapshots.append(PortfolioSnapshot.from_dict(raw_data))
            return snapshots
        except Exception as e:
            raise StorageReadError(
                f"[repositories] Failed to read history from Parquet '{self.file_path}': {e}"
            ) from e

    def save_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        """Appends a new portfolio snapshot to the Parquet file.

        Args:
            snapshot: PortfolioSnapshot instance to append.
        """
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            record: dict[str, Any] = {
                "timestamp": snapshot.timestamp,
                "total_value_eur": snapshot.total_value_eur,
                "snapshot_json": json.dumps(snapshot.to_dict()),
            }
            df_new: pd.DataFrame = pd.DataFrame([record])
            if self.file_path.exists():
                df_new.to_parquet(
                    str(self.file_path), engine="fastparquet", append=True, index=False
                )
            else:
                df_new.to_parquet(str(self.file_path), index=False)
        except Exception as e:
            raise StorageWriteError(
                f"[repositories] Failed to write history to Parquet '{self.file_path}': {e}"
            ) from e


class JsonPortfolioRepository:
    """JSON file-based implementation of PortfolioRepository."""

    def __init__(self, file_path: str | Path) -> None:
        """Initializes the JSON portfolio repository.

        Args:
            file_path: Path to the JSON portfolio file.
        """
        self.file_path: Path = Path(file_path)

    def load_assets(self) -> list[Asset]:
        """Loads assets from a local JSON portfolio file.

        Returns:
            A list of Asset instances.
        """
        if not self.file_path.exists():
            raise StorageReadError(f"[repositories] Portfolio file not found at '{self.file_path}'.")

        try:
            with open(self.file_path, encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
                return [Asset.from_dict(item) for item in data.get("assets", [])]
        except (json.JSONDecodeError, OSError) as e:
            raise StorageReadError(
                f"[repositories] Failed to read portfolio from '{self.file_path}': {e}"
            ) from e


class JsonHistoryRepository:
    """JSON file-based implementation of HistoryRepository."""

    def __init__(self, file_path: str | Path) -> None:
        """Initializes the JSON history repository.

        Args:
            file_path: Path to the JSON history file.
        """
        self.file_path: Path = Path(file_path)

    def load_history(self) -> list[PortfolioSnapshot]:
        """Loads history snapshots from a local JSON file.

        Returns:
            A list of PortfolioSnapshot instances.
        """
        if not self.file_path.exists():
            return []

        try:
            with open(self.file_path, encoding="utf-8") as f:
                data: list[dict[str, Any]] = json.load(f)
                return [PortfolioSnapshot.from_dict(item) for item in data]
        except (json.JSONDecodeError, OSError) as e:
            raise StorageReadError(
                f"[repositories] Failed to read history from '{self.file_path}': {e}"
            ) from e

    def save_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        """Appends a snapshot to the local JSON history file.

        Args:
            snapshot: PortfolioSnapshot instance to append.
        """
        history: list[PortfolioSnapshot] = self.load_history()
        history.append(snapshot)

        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                raw_data: list[dict[str, Any]] = [s.to_dict() for s in history]
                json.dump(raw_data, f, indent=2)
        except OSError as e:
            raise StorageWriteError(
                f"[repositories] Failed to write history to '{self.file_path}': {e}"
            ) from e


class JsonETFCacheRepository:
    """JSON file-based implementation of ETFCacheRepository with TTL validation."""

    def __init__(
        self,
        file_path: str | Path = ETF_CACHE_FILE,
        ttl_days: int | None = None,
    ) -> None:
        """Initializes the JSON ETF cache repository with TTL configuration.

        Args:
            file_path: Path to the cache JSON file.
            ttl_days: Cache Time-To-Live in days.
        """
        self.file_path: Path = Path(file_path)
        self.ttl_days: int = (
            ttl_days if ttl_days is not None else get_settings().etf_cache_ttl_days
        )

    def get_etf_details(self, isin: str) -> ETFDetails | None:
        """Retrieves cached ETF details for an ISIN if unexpired and valid.

        Args:
            isin: International Securities Identification Number.

        Returns:
            An ETFDetails instance if valid cache exists, None otherwise.
        """
        if not self.file_path.exists():
            return None

        try:
            with open(self.file_path, encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                f"[repositories] Corrupted or unreadable ETF cache file at '{self.file_path}': {e}"
            )
            return None

        entry: dict[str, Any] | None = data.get(isin)
        if not entry or not isinstance(entry, dict):
            return None

        cached_at_str: str | None = entry.get("cached_at")
        raw_details: Any = entry.get("details")

        if not cached_at_str or not isinstance(raw_details, dict):
            return None

        try:
            cached_at = datetime.fromisoformat(cached_at_str)
            if cached_at.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=UTC)

            now = datetime.now(UTC)
            age_days = (now - cached_at).total_seconds() / 86400.0

            if age_days > self.ttl_days:
                logger.info(
                    f"[repositories] Cache entry for ISIN {isin} expired ({age_days:.1f} days old)."
                )
                return None

            return ETFDetails.from_dict(raw_details)
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            logger.warning(f"[repositories] Failed to parse cached ETF details for ISIN {isin}: {e}")
            return None

    def save_etf_details(self, isin: str, details: ETFDetails) -> None:
        """Persists ETF details into the JSON cache file with current UTC timestamp.

        Args:
            isin: International Securities Identification Number.
            details: ETFDetails instance to cache.
        """
        cache_data: dict[str, Any] = {}

        if self.file_path.exists():
            try:
                with open(self.file_path, encoding="utf-8") as f:
                    cache_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                cache_data = {}

        cache_data[isin] = {
            "cached_at": datetime.now(UTC).isoformat(),
            "details": details.to_dict(),
        }

        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)
        except OSError as e:
            raise StorageWriteError(
                f"[repositories] Failed to write ETF cache to '{self.file_path}': {e}"
            ) from e


class SqliteOpportunityRepository:
    """SQLite database-backed implementation for persisting and querying
    opportunity evaluation reports and asset fundamentals cache.
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        """Initializes the SQLite opportunity repository.

        Args:
            db_path: Path to the SQLite database.
        """
        self.db_path: Path = Path(db_path)

    def save_opportunity_report(
        self,
        timestamp: str,
        total_value_eur: float,
        has_ai: bool,
        ranked_scores: list[Any],
        asset_dict_map: dict[str, dict[str, Any]],
        recommendations_map: dict[str, Any],
        advisories_map: dict[str, dict[str, Any]] | None = None,
        total_invested_eur: float = 0.0,
    ) -> None:
        """Saves a complete opportunity evaluation run and its per-asset metrics into SQLite.

        Inserts one row into opportunities (the run header) and one row per asset
        into opportunity_asset_metrics. Idempotent on duplicate timestamp via ON CONFLICT.

        Args:
            timestamp: ISO8601 run timestamp (unique key).
            total_value_eur: Portfolio market value at run time.
            has_ai: Whether AI scoring was enabled for this run.
            ranked_scores: Ordered list of score objects (must expose symbol, asset_type,
                dip_score, cost_score, allocation_score, total_score attributes).
            asset_dict_map: Dict of symbol → raw metric dict (price, allocations, ratios).
            recommendations_map: Dict of symbol → RebalanceRecommendation (or None).
            advisories_map: Optional dict of symbol → advisory dict for JSON storage.
            total_invested_eur: Total capital deployed at run time.

        Raises:
            StorageWriteError: If any database operation fails.
        """
        unrealized_pnl_eur: float = total_value_eur - total_invested_eur
        try:
            with get_db_context(str(self.db_path)) as conn:
                initialize_database(conn)
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO opportunities (
                        timestamp, total_invested_eur, total_value_eur,
                        unrealized_pnl_eur, has_ai
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(timestamp) DO NOTHING;
                    """,
                    (
                        timestamp,
                        total_invested_eur,
                        total_value_eur,
                        unrealized_pnl_eur,
                        1 if has_ai else 0,
                    ),
                )

                cursor.execute(
                    "SELECT id FROM opportunities WHERE timestamp = ?", (timestamp,)
                )
                row = cursor.fetchone()
                if not row:
                    return
                opportunity_id: int = int(row["id"])

                for rank, score in enumerate(ranked_scores, start=1):
                    symbol: str = str(score.symbol)
                    target_item: dict[str, Any] = asset_dict_map.get(symbol, {})
                    rec = recommendations_map.get(symbol)

                    adv_dict = (advisories_map or {}).get(symbol)
                    advisory_json_str: str | None = (
                        json.dumps(adv_dict) if adv_dict else None
                    )

                    cursor.execute(
                        """
                        INSERT INTO opportunity_asset_metrics (
                            opportunity_id, symbol, asset_type, rank, price_eur,
                            current_allocation_pct, target_allocation_pct,
                            dip_score, cost_score, gap_score, quant_score,
                            ai_action, ai_urgency, ai_confidence_pct,
                            forward_pe, trailing_pe, peg_ratio, price_to_book,
                            dividend_yield_pct, ter, advisory_json
                        )
                        VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                        )
                        """,
                        (
                            opportunity_id,
                            symbol,
                            str(score.asset_type.value).upper(),
                            rank,
                            float(target_item.get("current_price", 0.0)),
                            float(target_item.get("current_allocation_pct", 0.0)),
                            float(target_item.get("target_allocation_pct", 0.0)),
                            float(score.dip_score),
                            float(score.cost_score),
                            float(score.allocation_score),
                            float(score.total_score),
                            (str(rec.action.value) if rec and rec.action else None),
                            (
                                str(rec.urgency_level.value)
                                if rec and rec.urgency_level
                                else None
                            ),
                            (float(rec.confidence_score * 100.0) if rec else None),
                            target_item.get("forward_pe"),
                            target_item.get("trailing_pe"),
                            target_item.get("peg_ratio"),
                            target_item.get("price_to_book"),
                            target_item.get("dividend_yield_pct"),
                            target_item.get("ter"),
                            advisory_json_str,
                        ),
                    )
        except Exception as e:
            raise StorageWriteError(
                f"[repositories] Failed to save opportunity report to SQLite: {e}"
            ) from e

    def load_asset_history(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        """Loads historical opportunity metrics for a specific asset to enable trend analysis.

        Args:
            symbol: Asset ticker or symbol.
            limit: Maximum number of historical records to return.

        Returns:
            A list of dictionaries containing historical metric rows.
        """
        if not self.db_path.exists():
            return []

        try:
            with get_db_context(str(self.db_path)) as conn:
                initialize_database(conn)
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT o.timestamp, oam.rank, oam.price_eur, oam.quant_score,
                           oam.forward_pe, oam.dividend_yield_pct, oam.ai_action
                    FROM opportunity_asset_metrics oam
                    JOIN opportunities o ON oam.opportunity_id = o.id
                    WHERE oam.symbol = ?
                    ORDER BY o.timestamp DESC
                    LIMIT ?
                    """,
                    (symbol, limit),
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.warning(f"Failed to load asset history for '{symbol}': {e}")
            return []

    def load_latest_top_opportunities(self, limit: int = 5) -> list[dict[str, Any]]:
        """Loads the top-N ranked assets from the most recent opportunity run.

        Args:
            limit: Maximum number of top opportunities to return.

        Returns:
            A list of dictionaries representing top ranked assets.
        """
        if not self.db_path.exists():
            return []
        try:
            with get_db_context(str(self.db_path)) as conn:
                initialize_database(conn)
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT oam.symbol, oam.asset_type, oam.rank,
                           oam.price_eur, oam.quant_score, oam.ai_action
                    FROM opportunity_asset_metrics oam
                    JOIN opportunities o ON oam.opportunity_id = o.id
                    WHERE o.id = (SELECT MAX(id) FROM opportunities)
                    ORDER BY oam.rank ASC
                    LIMIT ?
                    """,
                    (limit,),
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"[repositories] Failed to load top opportunities: {e}")
            return []

    def get_asset_fundamentals(
        self,
        asset_id: int,
        asset_type: str,
        ttl_hours: int,
    ) -> ETFDetails | StockDetails | None:
        """Returns cached fundamentals for an asset if they are within the TTL window.

        Args:
            asset_id: Database primary key of the asset.
            asset_type: 'STOCK' or 'ETF' — controls which model is deserialized.
            ttl_hours: Maximum age in hours before the cache is considered stale.

        Returns:
            Deserialized ETFDetails or StockDetails if a fresh cache entry exists,
            None otherwise.
        """
        if not self.db_path.exists():
            return None

        try:
            with get_db_context(str(self.db_path)) as conn:
                initialize_database(conn)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT fetched_at, details_json, asset_type "
                    "FROM asset_fundamentals WHERE asset_id = ?",
                    (asset_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None

                fetched_at_str: str = str(row["fetched_at"])
                fetched_at: datetime = datetime.fromisoformat(fetched_at_str)
                age_hours: float = (
                    datetime.now(UTC) - fetched_at.replace(tzinfo=UTC)
                ).total_seconds() / 3600.0
                if age_hours > ttl_hours:
                    return None

                details_data: dict[str, Any] = json.loads(str(row["details_json"]))
                stored_type: str = str(row["asset_type"]).upper()
                if stored_type == "ETF":
                    return ETFDetails.from_dict(details_data)
                return StockDetails.from_dict(details_data)
        except Exception as e:
            logger.error(
                f"[repositories] Failed to load cached fundamentals for asset_id={asset_id}: {e}"
            )
            return None

    def upsert_asset_fundamentals(
        self,
        asset_id: int,
        asset_type: str,
        details: ETFDetails | StockDetails,
        quality_tier: str | None = None,
        quality_score: int | None = None,
    ) -> None:
        """Upserts the latest fundamentals for an asset into the cache table.

        Args:
            asset_id: Database primary key of the asset.
            asset_type: 'STOCK' or 'ETF'.
            details: Freshly fetched fundamental data.
            quality_tier: Evaluated quality tier (e.g., 'Tier A').
            quality_score: Evaluated quality score (0-100).
        """
        fetched_at_str: str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        details_json_str: str = json.dumps(details.to_dict())
        normalized_type: str = asset_type.upper()

        try:
            with get_db_context(str(self.db_path)) as conn:
                initialize_database(conn)
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO asset_fundamentals
                        (asset_id, asset_type, fetched_at, details_json,
                         quality_tier, quality_score)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(asset_id) DO UPDATE SET
                        asset_type = excluded.asset_type,
                        fetched_at = excluded.fetched_at,
                        details_json = excluded.details_json,
                        quality_tier = excluded.quality_tier,
                        quality_score = excluded.quality_score;
                    """,
                    (
                        asset_id,
                        normalized_type,
                        fetched_at_str,
                        details_json_str,
                        quality_tier,
                        quality_score,
                    ),
                )
            logger.success(
                f"[repositories] Upserted asset_fundamentals cache for asset_id={asset_id} "
                f"({normalized_type})."
            )
        except Exception as e:
            raise StorageWriteError(
                f"[repositories] Failed to upsert asset_fundamentals for asset_id={asset_id}: {e}"
            ) from e

    def save_stock_fundamentals(
        self,
        asset_id: int,
        details: StockDetails,
        quality_tier: str | None = None,
        quality_score: int | None = None,
    ) -> None:
        """Inserts a historical fundamental data snapshot for a specific stock asset.

        Args:
            asset_id: Database primary key of the asset in the assets table.
            details: Stock details object containing fundamental metrics.
            quality_tier: Evaluated absolute quality tier (e.g., Tier A).
            quality_score: Evaluated absolute quality score (0-100).
        """
        query: str = """
            INSERT INTO stock_fundamental_history (
                asset_id,
                fetched_at,
                market_cap,
                pe_ratio,
                forward_pe,
                price_to_book,
                peg_ratio,
                dividend_yield_pct,
                return_on_equity_pct,
                total_debt_to_equity,
                free_cashflow,
                beta,
                eps_trailing_ttm,
                fifty_two_week_high,
                fifty_two_week_low,
                sector,
                industry,
                quality_tier,
                quality_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        fetched_at_str: str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        params: tuple[Any, ...] = (
            asset_id,
            fetched_at_str,
            details.market_cap,
            details.pe_ratio,
            details.forward_pe,
            details.price_to_book,
            details.peg_ratio,
            details.dividend_yield_pct,
            details.return_on_equity_pct,
            details.total_debt_to_equity,
            details.free_cashflow,
            details.beta,
            details.eps_trailing_ttm,
            details.fifty_two_week_high,
            details.fifty_two_week_low,
            details.sector,
            details.industry,
            quality_tier,
            quality_score,
        )

        try:
            with get_db_context(str(self.db_path)) as conn:
                initialize_database(conn)
                cursor = conn.cursor()
                cursor.execute(query, params)

            logger.success(
                "[repositories] Successfully saved fundamental history snapshot for "
                f"asset_id={asset_id} with quality tier {quality_tier}."
            )
        except Exception as e:
            raise StorageWriteError(
                f"[repositories] Failed to save stock fundamentals to '{self.db_path}': {e}"
            ) from e

    def save_etf_fundamentals(
        self,
        asset_id: int,
        details: ETFDetails,
        quality_tier: str | None = None,
        quality_score: int | None = None,
    ) -> None:
        """Persists an ETF fundamental snapshot record into SQLite history.

        Args:
            asset_id: Database identifier of the ETF asset.
            details: ETF details containing TER, holdings, and breakdowns.
            quality_tier: Evaluated absolute quality tier (e.g., Tier A).
            quality_score: Evaluated absolute quality score (0-100).
        """
        query: str = """
            INSERT INTO etf_fundamental_history (
                asset_id,
                fetched_at,
                ter_pct,
                holdings_json,
                sector_breakdown_json,
                country_breakdown_json,
                quality_tier,
                quality_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        fetched_at_str: str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        holdings_data: list[dict[str, Any]] = (
            [h.to_dict() for h in details.holdings] if details.holdings else []
        )
        sector_data: list[dict[str, Any]] = (
            [s.to_dict() for s in details.sector_breakdown]
            if details.sector_breakdown
            else []
        )
        country_data: list[dict[str, Any]] = (
            [c.to_dict() for c in details.country_breakdown]
            if details.country_breakdown
            else []
        )

        params: tuple[Any, ...] = (
            asset_id,
            fetched_at_str,
            details.ter_pct,
            json.dumps(holdings_data),
            json.dumps(sector_data),
            json.dumps(country_data),
            quality_tier,
            quality_score,
        )

        try:
            with get_db_context(str(self.db_path)) as conn:
                initialize_database(conn)
                cursor = conn.cursor()
                cursor.execute(query, params)

            logger.success(
                "[repositories] Successfully saved ETF fundamental history snapshot for "
                f"asset_id={asset_id} with quality tier {quality_tier}."
            )
        except Exception as e:
            raise StorageWriteError(
                f"[repositories] Failed to save ETF fundamentals to '{self.db_path}': {e}"
            ) from e