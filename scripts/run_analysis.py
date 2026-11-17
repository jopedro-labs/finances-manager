"""Script for running complete portfolio performance and exposure analysis."""

from __future__ import annotations

import argparse
from pathlib import Path

from core.analysis import analyze_overall_performance
from infra.database.connection import DEFAULT_DB_PATH, get_db_context
from infra.database.schema import initialize_database


def main() -> None:
    """Bootstraps database and runs overall performance analytics."""
    parser = argparse.ArgumentParser(description="Run portfolio performance analysis.")
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Bypass cache and force live market data fetch.",
    )
    args = parser.parse_args()

    logger.section("[run analysis] Running Portfolio Analysis Pipeline")
    db_path = Path(DEFAULT_DB_PATH)

    with get_db_context(db_path) as conn:
        initialize_database(conn)

    # Se precisares de passar o force_refresh para os repositories/providers:
    if args.force_refresh:
        logger.info("[run analysis] Forced refresh enabled — bypassing cached data.")

    analyze_overall_performance()
    logger.success("[run analysis] Analysis completed successfully.")


if __name__ == "__main__":
    main()