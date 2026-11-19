"""Script for running deterministic portfolio opportunity analysis and ranking.

Evaluates latest snapshot allocations against strategic targets, executes
look-through ETF exposure analysis, computes penalty factors for policy limit breaches,
evaluates quantitative scores and decision matrix recommendations (core/scoring.py),
and persists the execution run into the SQLite opportunities repository.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure root workspace directory is in pythonpath
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core_lib.logger import logger  # noqa: E402

from config import DATA_DIR, get_settings  # noqa: E402
from core.data_collectors import ETFProvider, StockProvider  # noqa: E402
from core.exposure import ExposureEngine  # noqa: E402
from core.models import PortfolioSnapshot, ScoredAsset  # noqa: E402
from core.repositories import (  # noqa: E402
    SqliteHistoryRepository,
    SqliteOpportunityRepository,
    SqlitePortfolioRepository,
)
from core.scoring import score_etf, score_stock  # noqa: E402
from infra.database.connection import get_db_context  # noqa: E402
from infra.database.schema import initialize_database  # noqa: E402


def _load_targets_map() -> dict[str, float]:
    """Loads strategic allocation targets mapping by ISIN from portfolio_targets.json."""
    targets_file = DATA_DIR / "portfolio_targets.json"
    if not targets_file.exists():
        return {}
    try:
        with open(targets_file, encoding="utf-8") as f:
            data = json.load(f)
        return {
            item["isin"]: float(item.get("target_allocation_pct", 0.0))
            for item in data.get("assets", [])
            if item.get("isin")
        }
    except Exception as e:
        logger.warning(f"[run analysis] Could not load targets from '{targets_file}': {e}")
        return {}


def _calculate_exposure_penalties(
    snapshot: PortfolioSnapshot,
    exposure_engine: ExposureEngine,
    settings: Any,
) -> dict[str, float]:
    """Calculates multiplicative penalty factor (<= 1.0) for each asset based on exposure breaches."""
    sector_pcts, country_pcts = exposure_engine.calculate_consolidated_exposure(snapshot)
    penalties: dict[str, float] = {}

    for asset_snap in snapshot.assets_snapshot:
        penalty = 1.0
        isin = asset_snap.isin
        # Country breach penalty
        for _country, pct in country_pcts.items():
            if pct > settings.max_country_allocation_pct:
                penalty *= 1.0 - settings.exposure_country_penalty_weight
                break
        # Tech sector breach penalty
        tech_pct = sector_pcts.get("Technology", 0.0)
        if tech_pct > settings.max_tech_allocation_pct:
            penalty *= 1.0 - settings.exposure_sector_penalty_weight

        penalties[isin] = round(max(0.20, penalty), 4)
    return penalties


def main() -> None:
    """Runs deterministic opportunity ranking and persists results to SQLite."""
    parser = argparse.ArgumentParser(description="Run portfolio opportunity analysis.")
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Bypass cache and force live market data fetch.",
    )
    args = parser.parse_args()

    logger.section("[run analysis] Running Portfolio Opportunity Analysis Pipeline")
    settings = get_settings()
    db_path = settings.finance_db_file

    with get_db_context(str(db_path)) as conn:
        initialize_database(conn)

    portfolio_repo = SqlitePortfolioRepository(db_path)
    history_repo = SqliteHistoryRepository(db_path)
    opp_repo = SqliteOpportunityRepository(db_path)

    assets = portfolio_repo.load_assets()
    if not assets:
        logger.error(
            "[run analysis] No active assets found in SQLite database. Run make migrate first."
        )
        return

    history = history_repo.load_history()
    if not history:
        logger.error(
            "[run analysis] No snapshot history found in database. Run make snapshot first."
        )
        return

    latest_snapshot: PortfolioSnapshot = history[-1]
    targets_map = _load_targets_map()

    stock_provider = StockProvider()
    etf_provider = ETFProvider()
    exposure_engine = ExposureEngine(
        etf_provider=etf_provider,
        stock_provider=stock_provider,
        portfolio_repo=portfolio_repo,
    )

    penalties_map = _calculate_exposure_penalties(latest_snapshot, exposure_engine, settings)

    # Calculate current allocation percentages from latest snapshot
    total_market_val = latest_snapshot.total_market_value_eur
    current_allocations: dict[str, float] = {}
    current_prices: dict[str, float] = {}

    for snap_item in latest_snapshot.assets_snapshot:
        isin = snap_item.isin
        val = snap_item.market_value_eur
        alloc_pct = (val / total_market_val * 100.0) if total_market_val > 0 else 0.0
        current_allocations[isin] = alloc_pct
        current_prices[isin] = snap_item.market_price

    scored_assets: list[ScoredAsset] = []
    asset_dict_map: dict[str, dict[str, Any]] = {}
    recommendations_map: dict[str, Any] = {}

    for asset in assets:
        isin = asset.isin
        target_alloc = targets_map.get(isin, 0.0)
        current_alloc = current_allocations.get(isin, 0.0)
        price = current_prices.get(isin)
        penalty = penalties_map.get(isin, 1.0)

        # Fetch fundamentals and quality tier
        if asset.asset_type == "STOCK":
            stock_details = stock_provider.get_details(
                asset, force_refresh=args.force_refresh, db_path=db_path
            )
            if not stock_details:
                continue
            quality_tier = "Tier B"
            val_status = "Fair Value"

            scored = score_stock(
                asset=asset,
                details=stock_details,
                current_alloc_pct=current_alloc,
                target_alloc_pct=target_alloc,
                current_price=price,
                quality_tier=quality_tier,
                valuation_status=val_status,
                penalty_factor=penalty,
                settings=settings,
            )
            scored_assets.append(scored)
            symbol = scored.symbol
            recommendations_map[symbol] = scored.recommendation
            asset_dict_map[symbol] = {
                "current_price": price or 0.0,
                "current_allocation_pct": current_alloc,
                "target_allocation_pct": target_alloc,
                "forward_pe": stock_details.forward_pe,
                "trailing_pe": stock_details.pe_ratio,
                "peg_ratio": stock_details.peg_ratio,
                "price_to_book": stock_details.price_to_book,
                "dividend_yield_pct": stock_details.dividend_yield_pct,
                "ter": None,
            }

        elif asset.asset_type == "ETF":
            etf_details = etf_provider.get_details(
                asset, force_refresh=args.force_refresh, db_path=db_path
            )
            if not etf_details:
                continue
            quality_tier = "Tier A"
            val_status = "Fair Value"
            scored = score_etf(
                asset=asset,
                details=etf_details,
                current_alloc_pct=current_alloc,
                target_alloc_pct=target_alloc,
                current_price=price,
                peak_price=price,
                quality_tier=quality_tier,
                valuation_status=val_status,
                penalty_factor=penalty,
                settings=settings,
            )
            scored_assets.append(scored)
            symbol = scored.symbol
            recommendations_map[symbol] = scored.recommendation
            asset_dict_map[symbol] = {
                "current_price": price or 0.0,
                "current_allocation_pct": current_alloc,
                "target_allocation_pct": target_alloc,
                "forward_pe": None,
                "trailing_pe": None,
                "peg_ratio": None,
                "price_to_book": None,
                "dividend_yield_pct": None,
                "ter": etf_details.ter_pct,
            }

    # Sort by final score descending
    scored_assets.sort(key=lambda x: x.final_score, reverse=True)

    # Persist opportunity run to SQLite
    run_timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    opp_repo.save_opportunity_report(
        timestamp=run_timestamp,
        total_value_eur=total_market_val,
        has_ai=False,
        ranked_scores=[
            type(
                "ScoreObj",
                (),
                {
                    "symbol": s.symbol,
                    "asset_type": type("AssetTypeEnum", (), {"value": s.asset_type}),
                    "dip_score": s.dip_score,
                    "cost_score": s.cost_or_pe_score,
                    "allocation_score": s.allocation_score,
                    "total_score": s.final_score,
                },
            )()
            for s in scored_assets
        ],
        asset_dict_map=asset_dict_map,
        recommendations_map=recommendations_map,
        total_invested_eur=latest_snapshot.total_invested_eur,
    )

    logger.success(f"[run analysis] Opportunity report persisted to SQLite at {run_timestamp}.")

    # Print terminal overview
    logger.section("[run analysis] Opportunity Ranking & Rebalance Recommendations")
    for rank, item in enumerate(scored_assets, start=1):
        rec = item.recommendation
        logger.info(
            f"#{rank:<2} | {item.name:<30} | {item.asset_type:<5} | "
            f"Score: {item.final_score:.4f} | Action: {rec.action.value:<10} | "
            f"Conf: {rec.confidence_score * 100:>3.0f}% | {rec.reasoning[:50]}..."
        )


if __name__ == "__main__":
    main()
