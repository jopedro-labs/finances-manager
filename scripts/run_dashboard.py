"""Script for computing dashboard overview metrics and generating dashboard report."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure root workspace directory is in pythonpath
_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

from core_lib.logger import logger  # noqa: E402

from config import REPORTS_DIR, get_settings  # noqa: E402
from core.models import DashboardOverview  # noqa: E402
from core.portfolio_analytics import PortfolioAnalyticsEngine  # noqa: E402
from core.repositories import SqlitePortfolioRepository  # noqa: E402
from infra.database.connection import get_db_context  # noqa: E402
from infra.database.finance_sql_extraction import FinanceSQLExtractor  # noqa: E402
from infra.database.schema import initialize_database  # noqa: E402


def _generate_markdown_dashboard_report(
    overview: DashboardOverview,
    output_path: Path,
) -> None:
    """Generates a structured markdown report from dashboard analytics and saves it."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    val_history = overview.portfolio_history.value_history
    ath_history = overview.portfolio_history.ath_history
    dd_history = overview.portfolio_history.drawdown_history

    current_val = val_history[-1].value if val_history else 0.0
    current_ath = ath_history[-1].value if ath_history else 0.0
    current_dd = dd_history[-1].value if dd_history else 0.0
    invested_val = overview.latest_invested_eur
    pnl_eur = overview.latest_unrealized_pnl_eur
    pnl_pct = overview.latest_unrealized_pnl_pct
    pnl_sign = "+" if pnl_eur >= 0 else ""

    md: list[str] = [
        "# Portfolio Dashboard & Performance Analytics Report",
        "",
        f"> **Generated at:** {now_str}  ",
        f"> **Total Historical Snapshots:** {len(val_history)}  ",
        f"> **Current Portfolio Valuation:** €{current_val:,.2f}  ",
        f"> **Total Capital Invested:** €{invested_val:,.2f}  ",
        f"> **Unrealized P&L:** {pnl_sign}€{pnl_eur:,.2f} ({pnl_sign}{pnl_pct:.2f}%)  ",
        f"> **All-Time High (ATH):** €{current_ath:,.2f}  ",
        f"> **Current Drawdown from ATH:** {current_dd:.2f}% (Max Drawdown: **{overview.max_drawdown_percent:.2f}%**)  ",
        f"> **Top Absolute Growth Contributor:** `{overview.top_growth_contributor or 'N/A'}`",
        "",
        "## 1. Executive Summary & Portfolio KPIs",
        "",
        "| KPI Metric | Value |",
        "|---|---|",
        f"| **Current Valuation** | €{current_val:,.2f} |",
        f"| **Total Capital Invested** | €{invested_val:,.2f} |",
        f"| **Unrealized Gain / Loss** | {pnl_sign}€{pnl_eur:,.2f} ({pnl_sign}{pnl_pct:.2f}%) |",
        f"| **Peak Historical Valuation (ATH)** | €{current_ath:,.2f} |",
        f"| **Maximum Historical Drawdown** | {overview.max_drawdown_percent:.2f}% |",
        f"| **Top Growth Contributor (Absolute €)** | `{overview.top_growth_contributor or 'N/A'}` |",
        "",
        "---",
        "",
        "## 2. Asset Performance & Valuation Summary",
        "",
        "| Asset Name | Symbol / ISIN | Type | Quantity | Market Value | Cost Basis | Unrealized P&L (€) | ROI (%) | Portfolio Share |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    sorted_summaries = sorted(
        overview.asset_summaries, key=lambda s: s.latest_value_eur, reverse=True
    )
    for a in sorted_summaries:
        pnl_sign = "+" if a.roi_eur >= 0 else ""
        md.append(
            f"| **{a.name}** | `{a.isin}` | {a.asset_type} | {a.latest_quantity:,.4f} | "
            f"€{a.latest_value_eur:,.2f} | €{a.cost_basis_eur:,.2f} | "
            f"{pnl_sign}€{a.roi_eur:,.2f} | {pnl_sign}{a.roi_percent:.2f}% | {a.portfolio_share_percent:.2f}% |"
        )

    md.extend(
        [
            "",
            "---",
            "",
            "## 3. Asset Class Breakdown Evolution",
            "",
        ]
    )

    for class_ts in overview.class_series:
        latest_val = class_ts.value_history[-1].value if class_ts.value_history else 0.0
        latest_share = class_ts.share_history[-1].value if class_ts.share_history else 0.0
        md.append(
            f"### {class_ts.asset_type} Class (Current: €{latest_val:,.2f} — {latest_share:.2f}%)"
        )
        md.append("")
        md.append("| Snapshot Date | Valuation (€) | Portfolio Share (%) |")
        md.append("|---|---|---|")
        for val_pt, share_pt in zip(class_ts.value_history, class_ts.share_history, strict=False):
            md.append(f"| {val_pt.date} | €{val_pt.value:,.2f} | {share_pt.value:.2f}% |")
        md.append("")

    md.extend(
        [
            "---",
            "",
            "## 4. Portfolio Historical Evolution & Drawdown Track",
            "",
            "| Snapshot Date | Portfolio Value (€) | ATH (€) | Drawdown (%) |",
            "|---|---|---|---|",
        ]
    )

    for val_pt, ath_pt, dd_pt in zip(val_history, ath_history, dd_history, strict=False):
        md.append(
            f"| {val_pt.date} | €{val_pt.value:,.2f} | €{ath_pt.value:,.2f} | {dd_pt.value:.2f}% |"
        )

    md.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    logger.success(f"[run dashboard] Dashboard report successfully written to '{output_path}'.")


def main() -> None:
    """Extracts historical records and builds the dashboard overview metrics and report."""
    logger.section("[run dashboard] Building Dashboard Overview Dataset")
    settings = get_settings()
    db_path = settings.finance_db_file

    with get_db_context(db_path) as conn:
        initialize_database(conn)

    extractor = FinanceSQLExtractor(db_path)
    asset_history = extractor.fetch_asset_history()
    portfolio_history = extractor.fetch_portfolio_history()

    portfolio_repo = SqlitePortfolioRepository(db_path)
    current_assets = portfolio_repo.load_all_assets()

    engine = PortfolioAnalyticsEngine()
    overview = engine.build_dashboard_overview(
        asset_records=asset_history,
        portfolio_records=portfolio_history,
        current_assets=current_assets,
    )

    logger.info(
        f"[run dashboard] Historical snapshots processed: {len(overview.portfolio_history.value_history)}"
    )
    logger.info(f"[run dashboard] Maximum portfolio drawdown: {overview.max_drawdown_percent:.2f}%")

    output_report_path = REPORTS_DIR / "dashboard_report.md"
    _generate_markdown_dashboard_report(overview, output_report_path)


if __name__ == "__main__":
    main()
