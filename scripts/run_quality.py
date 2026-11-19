"""Script for evaluating asset fundamental quality tiers, scoring, and report generation.

Iterates across all configured portfolio assets, fetches fundamental metrics
(via StockProvider and ETFProvider with resilient fallback chains), computes
deterministic quality scores and tiers (Tier A/B/C), logs structured summaries,
persists results to the database (asset_fundamentals, stock_fundamental_history,
and etf_fundamental_history), and generates a comprehensive quality_report.md
in the reports/ directory.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

# Ensure root workspace directory is in pythonpath
_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

from core_lib.logger import logger  # noqa: E402

from config import DATA_DIR, REPORTS_DIR  # noqa: E402
from core.analysis import evaluate_etf_quality, evaluate_stock_quality  # noqa: E402
from core.data_collectors import ETFProvider, StockProvider  # noqa: E402
from core.models import Asset, ETFDetails, StockDetails  # noqa: E402
from core.repositories import (  # noqa: E402
    JsonPortfolioRepository,
    SqliteOpportunityRepository,
    SqlitePortfolioRepository,
)
from infra.database.connection import DEFAULT_DB_PATH, get_db_context  # noqa: E402
from infra.database.schema import initialize_database  # noqa: E402


def _parse_inception_date(date_str: str) -> date | None:
    """Resiliently parses an inception date string into a date object.

    Handles ISO formats (YYYY-MM-DD), slash formats (DD/MM/YYYY or YYYY/MM/DD),
    and extracts 4-digit years as a fallback.

    Args:
        date_str: Raw date string from fund facts or metadata.

    Returns:
        Parsed date object, or None if parsing fails.
    """
    clean_str = date_str.strip()
    try:
        return date.fromisoformat(clean_str)
    except ValueError:
        pass

    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(clean_str, fmt).date()
        except ValueError:
            pass

    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", clean_str)
    if year_match:
        try:
            return date(int(year_match.group(1)), 1, 1)
        except ValueError:
            pass

    return None


def _calculate_age_years(inception_date_str: str | None) -> float | None:
    """Calculates fund age in years from an inception date string.

    Args:
        inception_date_str: Inception date string or None.

    Returns:
        Age in years as a float, or None if unavailable.
    """
    if not inception_date_str:
        return None
    parsed_date = _parse_inception_date(inception_date_str)
    if not parsed_date:
        return None
    return (date.today() - parsed_date).days / 365.25


def _get_asset_id(conn: sqlite3.Connection, asset: Asset) -> int | None:
    """Finds the database primary key ID for an asset by ISIN or Yahoo ticker.

    Args:
        conn: Active sqlite3 connection.
        asset: Domain Asset instance.

    Returns:
        Asset integer ID if found, None otherwise.
    """
    cur = conn.cursor()
    if asset.isin:
        cur.execute("SELECT id FROM assets WHERE isin = ?", (asset.isin,))
        row = cur.fetchone()
        if row:
            return int(row["id"])

    if asset.yahoo_ticker:
        cur.execute("SELECT id FROM assets WHERE yahoo_ticker = ?", (asset.yahoo_ticker,))
        row = cur.fetchone()
        if row:
            return int(row["id"])

    return None


def _format_pct(val: float | None) -> str:
    """Formats an optional float as percentage string."""
    return f"{val:.2f}%" if val is not None else "N/A"


def _format_num(val: float | None, decimals: int = 2) -> str:
    """Formats an optional float with specified decimals."""
    return f"{val:.{decimals}f}" if val is not None else "N/A"


def _format_currency(val: float | None, unit: str = "M€") -> str:
    """Formats an optional large monetary value."""
    return f"{val:,.1f}{unit}" if val is not None else "N/A"


def _generate_markdown_report(evaluations: list[dict[str, Any]], output_path: Path) -> None:
    """Generates a structured markdown report from evaluated assets and saves it.

    Args:
        evaluations: List of dictionaries with asset info, raw details, and evaluation output.
        output_path: Target Path where the quality_report.md should be written.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Aggregate counts
    tier_counts: dict[str, int] = {"Tier A": 0, "Tier B": 0, "Tier C": 0, "Unknown": 0}
    type_counts: dict[str, int] = {"STOCK": 0, "ETF": 0}

    for item in evaluations:
        t = item["eval"].get("tier", "Unknown")
        tier_counts[t] = tier_counts.get(t, 0) + 1
        asset_type = item["asset"].asset_type.upper()
        type_counts[asset_type] = type_counts.get(asset_type, 0) + 1

    md: list[str] = [
        "# Fundamental Quality Evaluation Report",
        "",
        f"> **Generated at:** {now_str}  ",
        f"> **Total Assets Evaluated:** {len(evaluations)} ({type_counts.get('STOCK', 0)} Stocks, {type_counts.get('ETF', 0)} ETFs)",
        "",
        "## 1. Executive Summary & Quality Distribution",
        "",
        "| Quality Tier | Count | Description |",
        "|---|---|---|",
        f"| **Tier A** (Top Quality) | {tier_counts.get('Tier A', 0)} | High profitability, low leverage or ultra-low cost, proven fund history |",
        f"| **Tier B** (Acceptable Quality) | {tier_counts.get('Tier B', 0)} | Moderate margins or balanced growth/risk profile |",
        f"| **Tier C** (Weak / Speculative) | {tier_counts.get('Tier C', 0)} | Negative margins, elevated leverage, high TER or small fund scale |",
        "",
        "---",
        "",
        "## 2. Asset Quality Overview",
        "",
        "| Asset Name | Symbol / ISIN | Type | Quality Tier | Score | Valuation / Key Metric |",
        "|---|---|---|---|---|---|",
    ]

    for item in evaluations:
        asset: Asset = item["asset"]
        res = item["eval"]
        symbol = asset.yahoo_ticker or asset.isin or "-"
        tier = res.get("tier", "N/A")
        score = f"{res.get('score', 0)}/{res.get('max_score', 100)}"

        if asset.asset_type == "STOCK":
            key_metric = res.get("valuation_status", "N/A")
        else:
            details: ETFDetails = item["details"]
            ter_str = f"TER: {details.ter_pct:.2f}%" if details.ter_pct is not None else "TER: N/A"
            key_metric = f"{ter_str} | {res.get('valuation_status', 'N/A')}"

        md.append(
            f"| **{asset.name}** | `{symbol}` | {asset.asset_type} | **{tier}** | `{score}` | {key_metric} |"
        )

    md.extend(
        [
            "",
            "---",
            "",
            "## 3. Deep-Dive Asset Evaluations",
            "",
        ]
    )

    for item in evaluations:
        asset = item["asset"]
        res = item["eval"]
        details = item["details"]
        tier = res.get("tier", "N/A")
        score = res.get("score", 0)
        max_score = res.get("max_score", 100)
        val_status = res.get("valuation_status", "N/A")

        md.append(f"### {asset.name} (`{asset.yahoo_ticker or asset.isin}`)")
        md.append(f"- **Asset Type:** {asset.asset_type}")
        md.append(f"- **Quality Tier:** **{tier}** (Score: **{score}/{max_score}**)")
        md.append(f"- **Valuation Assessment:** {val_status}")

        if asset.asset_type == "STOCK" and isinstance(details, StockDetails):
            md.append("")
            md.append("#### Fundamental Metrics:")
            md.append("| Metric | Value | Metric | Value |")
            md.append("|---|---|---|---|")
            md.append(
                f"| Operating Margin | {_format_pct(details.operating_margins_pct)} | Profit Margin | {_format_pct(details.profit_margins_pct)} |"
            )
            md.append(
                f"| Revenue Growth (YoY) | {_format_pct(details.revenue_growth_pct)} | Earnings Growth (YoY) | {_format_pct(details.earnings_growth_pct)} |"
            )
            md.append(
                f"| Total Debt / Equity | {_format_num(details.total_debt_to_equity)} | Return on Equity (ROE) | {_format_pct(details.return_on_equity_pct)} |"
            )
            md.append(
                f"| Trailing P/E | {_format_num(details.pe_ratio)} | Forward P/E | {_format_num(details.forward_pe)} |"
            )
            md.append(
                f"| Price to Book (P/B) | {_format_num(details.price_to_book)} | PEG Ratio | {_format_num(details.peg_ratio)} |"
            )
            md.append(
                f"| Dividend Yield | {_format_pct(details.dividend_yield_pct)} | Beta | {_format_num(details.beta)} |"
            )
            md.append(
                f"| Sector / Industry | {details.sector or 'N/A'} / {details.industry or 'N/A'} | Country | {details.country or 'N/A'} |"
            )

        elif asset.asset_type == "ETF" and isinstance(details, ETFDetails):
            md.append("")
            md.append("#### Fund Composition & Characteristics:")
            md.append("| Metric | Value | Metric | Value |")
            md.append("|---|---|---|---|")
            md.append(
                f"| Total Expense Ratio (TER) | {_format_pct(details.ter_pct)} | Fund Size (AUM) | {_format_currency(details.fund_size_eur_m)} |"
            )
            md.append(
                f"| Inception Date | {details.inception_date or 'N/A'} | Holdings Count | {details.holdings_count or 'N/A'} |"
            )
            md.append(
                f"| Replication | {details.replication or 'N/A'} | Distribution Policy | {details.distribution_policy or 'N/A'} |"
            )
            md.append(
                f"| Fund Currency | {details.fund_currency or 'N/A'} | Volatility (1 Year) | {_format_pct(details.volatility_1y_pct)} |"
            )

        bull_cases = res.get("bull_case", [])
        bear_cases = res.get("bear_case", [])

        md.append("")
        md.append("#### Investment Thesis & Findings:")
        if bull_cases:
            md.append("**Strengths & Bull Case Drivers:**")
            for b in bull_cases:
                md.append(f"- [x] {b}")
        if bear_cases:
            md.append("**Risks & Bear Case Considerations:**")
            for b in bear_cases:
                md.append(f"- [!] {b}")

        md.append("")
        md.append("---")
        md.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    logger.success(f"[run quality] Quality report successfully written to '{output_path}'.")


def load_target_assets(db_path: Path) -> list[Asset]:
    """Loads active portfolio assets with priority given to SQLite assets table.

    Falls back to data/portfolio.json if SQLite assets table is empty.

    Args:
        db_path: Path to SQLite database.

    Returns:
        List of Asset domain objects.
    """
    if db_path.exists():
        sqlite_repo = SqlitePortfolioRepository(db_path)
        assets = sqlite_repo.load_all_assets()
        if assets:
            logger.info(f"[run quality] Loaded {len(assets)} active assets from SQLite database.")
            return assets

    portfolio_file = DATA_DIR / "portfolio.json"
    if portfolio_file.exists():
        json_repo = JsonPortfolioRepository(portfolio_file)
        assets = json_repo.load_assets()
        logger.info(f"[run quality] Loaded {len(assets)} assets from '{portfolio_file}'.")
        return assets

    return []


def main() -> None:
    """Runs fundamental quality evaluations across configured portfolio assets."""
    parser = argparse.ArgumentParser(
        description="Evaluate asset fundamental quality tiers, persist ratings and generate quality report."
    )
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

    assets = load_target_assets(db_path)
    if not assets:
        logger.error("[run quality] No assets found to evaluate. Aborting.")
        return

    stock_provider = StockProvider()
    etf_provider = ETFProvider()
    opp_repo = SqliteOpportunityRepository(db_path=db_path)

    evaluated_records: list[dict[str, Any]] = []

    for asset in assets:
        if asset.asset_type == "STOCK":
            stock_details = stock_provider.get_details(
                asset, force_refresh=args.force_refresh, db_path=db_path
            )
            if stock_details is None:
                logger.warning(
                    f"[run quality] Could not fetch details for {asset.name} ({asset.yahoo_ticker}). Skipping."
                )
                continue

            result = evaluate_stock_quality(stock_details)
            tier: str = str(result["tier"])
            score: int = int(result["score"])
            status: str = str(result.get("valuation_status", ""))

            logger.info(
                f"[run quality] {asset.name:<30} | {asset.asset_type:<5} "
                f"| Tier: {tier:<6} | Score: {score:>3}/100 | {status}"
            )

            evaluated_records.append(
                {
                    "asset": asset,
                    "details": stock_details,
                    "eval": result,
                }
            )

            # Persist evaluation to database
            try:
                with get_db_context(db_path) as conn:
                    asset_id = _get_asset_id(conn, asset)

                if asset_id is not None:
                    opp_repo.upsert_asset_fundamentals(
                        asset_id=asset_id,
                        asset_type="STOCK",
                        details=stock_details,
                        quality_tier=tier,
                        quality_score=score,
                    )
                    opp_repo.save_stock_fundamentals(
                        asset_id=asset_id,
                        details=stock_details,
                        quality_tier=tier,
                        quality_score=score,
                    )
            except Exception as e:
                logger.warning(
                    f"[run quality] Failed to persist fundamentals for '{asset.name}': {e}"
                )

        elif asset.asset_type == "ETF":
            etf_details = etf_provider.get_details(
                asset, force_refresh=args.force_refresh, db_path=db_path
            )
            if etf_details is None:
                logger.warning(
                    f"[run quality] Could not fetch details for {asset.name} ({asset.isin}). Skipping."
                )
                continue

            aum_eur = (
                (etf_details.fund_size_eur_m or 0.0) * 1_000_000.0
                if etf_details.fund_size_eur_m
                else None
            )
            age_years = _calculate_age_years(etf_details.inception_date)

            result = evaluate_etf_quality(etf_details, aum_eur=aum_eur, age_years=age_years)
            tier = str(result["tier"])
            score = int(result["score"])
            ter_str = f"{etf_details.ter_pct:.2f}%" if etf_details.ter_pct is not None else "N/A"

            logger.info(
                f"[run quality] {asset.name:<30} | {asset.asset_type:<5} "
                f"| Tier: {tier:<6} | Score: {score:>3}/100 | TER: {ter_str}"
            )

            evaluated_records.append(
                {
                    "asset": asset,
                    "details": etf_details,
                    "eval": result,
                }
            )

            # Persist evaluation to database
            try:
                with get_db_context(db_path) as conn:
                    asset_id = _get_asset_id(conn, asset)

                if asset_id is not None:
                    opp_repo.upsert_asset_fundamentals(
                        asset_id=asset_id,
                        asset_type="ETF",
                        details=etf_details,
                        quality_tier=tier,
                        quality_score=score,
                    )
                    opp_repo.save_etf_fundamentals(
                        asset_id=asset_id,
                        details=etf_details,
                        quality_tier=tier,
                        quality_score=score,
                    )
            except Exception as e:
                logger.warning(
                    f"[run quality] Failed to persist ETF fundamentals for '{asset.name}': {e}"
                )

    # Generate Markdown Report in reports/quality_report.md
    if evaluated_records:
        report_file = REPORTS_DIR / "quality_report.md"
        _generate_markdown_report(evaluated_records, report_file)

    logger.success("[run quality] Fundamental quality evaluation pipeline executed successfully.")


if __name__ == "__main__":
    main()
