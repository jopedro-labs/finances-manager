"""Script for computing dashboard overview metrics and time-series aggregates."""

from __future__ import annotations

from pathlib import Path

from core_lib.logger import logger

from core.portfolio_analytics import PortfolioAnalyticsEngine
from infra.database.connection import DEFAULT_DB_PATH, get_db_context
from infra.database.finance_sql_extraction import FinanceSQLExtractor
from infra.database.schema import initialize_database


def main() -> None:
    """Extracts historical records and builds the dashboard overview metrics."""
    logger.section("[run dashboard] Building Dashboard Overview Dataset")
    db_path = Path(DEFAULT_DB_PATH)

    with get_db_context(db_path) as conn:
        initialize_database(conn)

    extractor = FinanceSQLExtractor(db_path)
    asset_history = extractor.fetch_asset_history()
    portfolio_history = extractor.fetch_portfolio_history()

    engine = PortfolioAnalyticsEngine()
    overview = engine.build_dashboard_overview(asset_history, portfolio_history)

    logger.info(
        f"[run dashboard] Total history points recorded: {len(overview.portfolio_history.value_history)}"
    )
    logger.info(f"[run dashboard] Maximum portfolio drawdown: {overview.max_drawdown_percent:.2f}%")
    logger.success("[run dashboard] Dashboard metrics computed successfully.")


if __name__ == "__main__":
    main()
