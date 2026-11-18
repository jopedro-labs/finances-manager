"""Script for evaluating asset fundamental quality tiers and scoring."""

from __future__ import annotations

import argparse
from pathlib import Path

from core_lib.logger import logger

from core.analysis import evaluate_etf_quality, evaluate_stock_quality
from core.data_collectors import ETFProvider, StockProvider
from core.repositories import JsonPortfolioRepository
from infra.database.connection import DEFAULT_DB_PATH, get_db_context
from infra.database.schema import initialize_database


def main() -> None:
    """Runs fundamental quality evaluations across configured portfolio assets."""
    parser = argparse.ArgumentParser(description="Evaluate asset fundamental quality tiers.")
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Bypass cache and force live fundamentals fetch from APIs.",
    )
    args = parser.parse_args()

    logger.section("[run quality] Running Fundamental Quality Evaluations")
    db_path = Path(DEFAULT_DB_PATH)

    with get_db_context(db_path) as conn:
        initialize_database(conn)

    if args.force_refresh:
        logger.info("[run quality] Forced refresh enabled for fundamental metrics.")

    assets = JsonPortfolioRepository().load_assets()
    if not assets:
        logger.error("[run quality] No assets found in portfolio.json. Aborting.")
        return

    stock_provider = StockProvider()
    etf_provider = ETFProvider()

    for asset in assets:
        if asset.asset_type == "STOCK":
            details = stock_provider.get_details(
                asset, force_refresh=args.force_refresh, db_path=db_path
            )
            if details is None:
                logger.warning(f"[run quality] Could not fetch details for {asset.name} ({asset.yahoo_ticker}). Skipping.")
                continue
            result = evaluate_stock_quality(details)
            logger.info(
                f"[run quality] {asset.name:<30} | {asset.asset_type:<5} "
                f"| Tier: {result['tier']:<6} | Score: {result['score']:>3}/100"
                f" | {result['valuation_status']}"
            )

        elif asset.asset_type == "ETF":
            details = etf_provider.get_details(
                asset, force_refresh=args.force_refresh, db_path=db_path
            )
            if details is None:
                logger.warning(f"[run quality] Could not fetch details for {asset.name} ({asset.isin}). Skipping.")
                continue
            aum_eur = (details.fund_size_eur_m or 0.0) * 1_000_000.0 if details.fund_size_eur_m else None
            age_years: float | None = None
            if details.inception_date:
                from datetime import date
                try:
                    inception = date.fromisoformat(details.inception_date)
                    age_years = (date.today() - inception).days / 365.25
                except ValueError:
                    age_years = None
            result = evaluate_etf_quality(details, aum_eur=aum_eur, age_years=age_years)
            ter_str = f"{details.ter_pct:.2f}%" if details.ter_pct is not None else "N/A"
            logger.info(
                f"[run quality] {asset.name:<30} | {asset.asset_type:<5} "
                f"| Tier: {result['tier']:<6} | Score: {result['score']:>3}/100 | TER: {ter_str}"
            )

    logger.success("[run quality] Fundamental quality evaluation pipeline executed successfully.")


if __name__ == "__main__":
    main()
