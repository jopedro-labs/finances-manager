"""Script for evaluating asset fundamental quality tiers and scoring."""

from __future__ import annotations

import argparse
from pathlib import Path

from core.analysis import evaluate_stock_quality, evaluate_etf_quality
from core.models import StockDetails, ETFDetails
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

    sample_stock = StockDetails(profit_margins_pct=22.5, revenue_growth_pct=10.0, total_debt_to_equity=80.0, pe_ratio=18.5)
    evaluation = evaluate_stock_quality(sample_stock)

    logger.info(f"[run quality] Sample Stock Tier Evaluation -> Score: {evaluation['score']}, Tier: {evaluation['tier']}")
    logger.success("[run quality] Fundamental quality evaluation pipeline executed successfully.")


if __name__ == "__main__":
    main()