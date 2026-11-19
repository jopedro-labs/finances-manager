"""Script for executing compound growth and wealth accumulation projections."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure root workspace directory is in pythonpath
_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

from core_lib.logger import logger

from config import REPORTS_DIR, get_settings
from core.projections import ProjectionEngine
from infra.database.connection import get_db_context
from infra.database.finance_sql_extraction import FinanceSQLExtractor
from infra.database.schema import initialize_database

SCENARIOS = [
    ("Conservative", 0.05),
    ("Realistic", 0.08),
    ("Optimistic", 0.11),
]
HORIZONS = [10, 20, 30]


def _generate_markdown_projections_report(
    current_val: float,
    monthly_contribution: float,
    inflation_rate: float,
    scenarios_data: list[tuple[str, float, Any]],
    output_path: Path,
) -> None:
    """Generates a structured markdown report for multi-horizon compound growth projections."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    md: list[str] = [
        "# Long-Term Portfolio Wealth & Growth Projections Report",
        "",
        f"> **Generated at:** {now_str}  ",
        f"> **Baseline Portfolio Valuation (PV):** €{current_val:,.2f}  ",
        f"> **Monthly Contribution (PMT):** €{monthly_contribution:,.2f}/month (€{monthly_contribution * 12:,.2f}/year)  ",
        f"> **Inflation Adjustment:** {inflation_rate * 100:.1f}% per year",
        "",
        "## 1. Executive Summary & Compound Growth Matrix (3×3)",
        "",
        "| Horizon | Conservative (5.0%) | Realistic (8.0%) | Optimistic (11.0%) | Total Capital Injected |",
        "|---|---|---|---|---|",
    ]

    for horizon in HORIZONS:
        total_invested = current_val + (monthly_contribution * 12 * horizon)
        c_val = next(
            s[2].milestones[horizon].projected_value
            for s in scenarios_data
            if s[0] == "Conservative"
        )
        r_val = next(
            s[2].milestones[horizon].projected_value
            for s in scenarios_data
            if s[0] == "Realistic"
        )
        o_val = next(
            s[2].milestones[horizon].projected_value
            for s in scenarios_data
            if s[0] == "Optimistic"
        )
        md.append(
            f"| **{horizon} Years** | €{c_val:,.0f} | **€{r_val:,.0f}** | €{o_val:,.0f} | €{total_invested:,.0f} |"
        )

    md.extend(
        [
            "",
            "---",
            "",
            "## 2. Detailed Breakdown by Scenario",
            "",
        ]
    )

    for name, annual_rate, scenario in scenarios_data:
        md.append(f"### {name} Scenario ({annual_rate * 100:.1f}% p.a.)")
        md.append("")
        md.append(
            "| Horizon | Nominal Projected Value | Inflation-Adjusted (Real) | Total Capital Invested | Compound Interest Earned |"
        )
        md.append("|---|---|---|---|---|")
        for horizon in HORIZONS:
            m = scenario.milestones[horizon]
            md.append(
                f"| {horizon} Years | €{m.projected_value:,.2f} | €{m.inflation_adjusted_value:,.2f} | "
                f"€{m.total_invested:,.2f} | **€{m.compound_interest:,.2f}** |"
            )
        md.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    logger.success(f"[run projections] Projections report successfully written to '{output_path}'.")


def main() -> None:
    """Extracts current portfolio value and calculates multi-scenario growth projections."""
    logger.section("[run projections] Calculating Portfolio Growth Projections")
    settings = get_settings()
    db_path = settings.finance_db_file
    monthly_contribution = settings.monthly_contribution
    inflation_rate = settings.inflation_rate

    with get_db_context(db_path) as conn:
        initialize_database(conn)

    extractor = FinanceSQLExtractor(db_path)
    portfolio_history = extractor.fetch_portfolio_history()

    current_val = portfolio_history[-1].total_value_eur if portfolio_history else 10000.0
    logger.info(f"[run projections] Baseline valuation: {current_val:,.2f} EUR (SQLite Source of Truth)")

    engine = ProjectionEngine()
    scenarios_data: list[tuple[str, float, Any]] = []

    for name, annual_rate in SCENARIOS:
        scenario = engine.generate_scenario(
            name=name,
            initial_value=current_val,
            monthly_contribution=monthly_contribution,
            annual_rate=annual_rate,
            horizons=HORIZONS,
            inflation_rate=inflation_rate,
        )
        scenarios_data.append((name, annual_rate, scenario))

    output_report_path = REPORTS_DIR / "projections_report.md"
    _generate_markdown_projections_report(
        current_val=current_val,
        monthly_contribution=monthly_contribution,
        inflation_rate=inflation_rate,
        scenarios_data=scenarios_data,
        output_path=output_report_path,
    )


if __name__ == "__main__":
    main()
