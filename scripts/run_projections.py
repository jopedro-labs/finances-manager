"""Script for executing compound growth and wealth accumulation projections."""

from __future__ import annotations

from pathlib import Path

from core_lib.logger import logger

from core.projections import ProjectionEngine
from infra.database.connection import DEFAULT_DB_PATH, get_db_context
from infra.database.finance_sql_extraction import FinanceSQLExtractor
from infra.database.schema import initialize_database

SCENARIOS = [
    ("Conservative", 0.05),
    ("Realistic", 0.08),
    ("Optimistic", 0.11),
]
HORIZONS = [10, 20, 30]
MONTHLY_CONTRIBUTION = 300.0
INFLATION_RATE = 0.02


def main() -> None:
    """Extracts current portfolio value and calculates multi-scenario growth projections."""
    logger.section("[run projections] Calculating Portfolio Growth Projections")
    db_path = Path(DEFAULT_DB_PATH)

    with get_db_context(db_path) as conn:
        initialize_database(conn)

    extractor = FinanceSQLExtractor(db_path)
    portfolio_history = extractor.fetch_portfolio_history()

    current_val = portfolio_history[-1].total_value_eur if portfolio_history else 10000.0
    logger.info(f"[run projections] Baseline valuation: {current_val:,.2f} EUR")
    logger.info(
        f"[run projections] Assumptions → Monthly Contribution: {MONTHLY_CONTRIBUTION:,.0f} EUR/month"
        f" | Inflation: {INFLATION_RATE * 100:.0f}%/year"
    )

    engine = ProjectionEngine()

    for name, annual_rate in SCENARIOS:
        scenario = engine.generate_scenario(
            name=name,
            initial_value=current_val,
            monthly_contribution=MONTHLY_CONTRIBUTION,
            annual_rate=annual_rate,
            horizons=HORIZONS,
            inflation_rate=INFLATION_RATE,
        )
        logger.info(f"\n[run projections] ── {name} ({annual_rate * 100:.0f}% p.a.) ──")
        logger.info(
            f"  {'Horizon':<10} {'Nominal':>14} {'Real (2% inf.)':>16}"
            f" {'Total Invested':>16} {'Compound Interest':>18}"
        )
        logger.info(f"  {'-' * 68}")
        for horizon in HORIZONS:
            m = scenario.milestones[horizon]
            logger.info(
                f"  {horizon} years    "
                f"{m.projected_value:>13,.0f} EUR"
                f"  {m.inflation_adjusted_value:>13,.0f} EUR"
                f"  {m.total_invested:>13,.0f} EUR"
                f"  {m.compound_interest:>16,.0f} EUR"
            )

    logger.success("[run projections] Growth projection scenarios evaluated successfully.")


if __name__ == "__main__":
    main()
