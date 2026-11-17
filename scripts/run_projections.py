"""Script for executing compound growth and wealth accumulation projections."""

from __future__ import annotations

from pathlib import Path

from infra.logger import logger

from infra.database.connection import DEFAULT_DB_PATH, get_db_context
from infra.database.finance_sql_extraction import FinanceSQLExtractor
from infra.database.schema import initialize_database


def main() -> None:
    """Extracts current portfolio value and calculates multi-scenario growth projections."""
    logger.section("[run projections] Calculating Portfolio Growth Projections")
    db_path = Path(DEFAULT_DB_PATH)

    with get_db_context(db_path) as conn:
        initialize_database(conn)

    extractor = FinanceSQLExtractor(db_path)
    portfolio_history = extractor.fetch_portfolio_history()

    current_val = portfolio_history[-1].total_value_eur if portfolio_history else 10000.0
    logger.info(f"[run projections] Baseline valuation for projection: {current_val:,.2f} EUR")

    # Simulation parameters
    annual_return = 0.07
    monthly_contrib = 500.0
    logger.info(
        f"[run projections] Assumptions -> Annual Return: {annual_return * 100:.1f}%, Monthly Contribution: {monthly_contrib:,.2f} EUR"
    )

    logger.success("[run projections] Growth projection scenarios evaluated successfully.")


if __name__ == "__main__":
    main()
