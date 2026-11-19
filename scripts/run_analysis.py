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

from config import DATA_DIR, REPORTS_DIR, get_settings  # noqa: E402
from core.analysis import evaluate_etf_quality, evaluate_stock_quality  # noqa: E402
from core.data_collectors import ETFProvider, StockProvider  # noqa: E402
from core.exposure import ExposureEngine  # noqa: E402
from core.models import Asset, PortfolioSnapshot, ScoredAsset  # noqa: E402
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
    sector_pcts: dict[str, float],
    country_pcts: dict[str, float],
    snapshot: PortfolioSnapshot,
    settings: Any,
) -> dict[str, float]:
    """Calculates multiplicative penalty factor (<= 1.0) for each asset based on exposure breaches."""
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


def _generate_markdown_analysis_report(
    snapshot: PortfolioSnapshot,
    scored_assets: list[ScoredAsset],
    assets: list[Asset],
    sector_pcts: dict[str, float],
    country_pcts: dict[str, float],
    penalties_map: dict[str, float],
    current_allocations: dict[str, float],
    targets_map: dict[str, float],
    output_path: Path,
) -> None:
    """Generates a structured markdown report from opportunity analysis and saves it.

    Args:
        snapshot: Current portfolio snapshot.
        scored_assets: Ranked list of ScoredAsset objects.
        sector_pcts: Value-weighted consolidated sector allocation percentages.
        country_pcts: Value-weighted consolidated country allocation percentages.
        penalties_map: Mapping of ISIN to calculated exposure penalty factor.
        current_allocations: Mapping of ISIN to current allocation percentage.
        targets_map: Mapping of ISIN to target allocation percentage.
        output_path: Path where analysis_report.md should be written.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    total_val = snapshot.total_market_value_eur
    total_inv = snapshot.total_invested_eur
    pnl_eur = snapshot.unrealized_pnl_eur
    pnl_pct = snapshot.unrealized_pnl_pct

    stocks_count = sum(1 for a in scored_assets if a.asset_type == "STOCK")
    etfs_count = sum(1 for a in scored_assets if a.asset_type == "ETF")

    md: list[str] = [
        "# Portfolio Opportunity & Performance Analysis Report",
        "",
        f"> **Generated at:** {now_str}  ",
        f"> **Snapshot Date:** {snapshot.timestamp.split('T')[0]}  ",
        f"> **Total Assets Analyzed:** {len(scored_assets)} ({stocks_count} Stocks, {etfs_count} ETFs)",
        "",
        "## 1. Executive Macro Summary & Portfolio KPIs",
        "",
        "| Portfolio Metric | Value |",
        "|---|---|",
        f"| **Total Market Value** | €{total_val:,.2f} |",
        f"| **Total Invested Capital** | €{total_inv:,.2f} |",
        f"| **Unrealized Gain / Loss** | €{pnl_eur:+,.2f} ({pnl_pct:+.2f}%) |",
        "",
        "---",
        "",
        "## 2. Exposure & Concentration Limits",
        "",
        "### Geographic Exposure (Look-Through)",
        "| Country | Weight % | Policy Ceiling | Status |",
        "|---|---|---|---|",
    ]

    for country, pct in sorted(country_pcts.items(), key=lambda x: x[1], reverse=True):
        status = "⚠️ **BREACH**" if pct > 60.0 else "✅ Compliant"
        md.append(f"| {country} | {pct:.1f}% | 60.0% | {status} |")

    md.extend(
        [
            "",
            "### Sector Exposure",
            "| Sector | Weight % | Policy Ceiling | Status |",
            "|---|---|---|---|",
        ]
    )

    for sector, pct in sorted(sector_pcts.items(), key=lambda x: x[1], reverse=True):
        ceiling = 50.0 if sector == "Technology" else 20.0
        status = "⚠️ **BREACH**" if pct > ceiling else "✅ Compliant"
        md.append(f"| {sector} | {pct:.1f}% | {ceiling:.1f}% | {status} |")

    md.extend(
        [
            "",
            "---",
            "",
            "## 3. Opportunity Ranking & Rebalance Recommendations",
            "",
            "| Rank | Asset Name | Symbol | Type | Current % | Target % | Score | Recommendation | Confidence |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
    )

    for rank, item in enumerate(scored_assets, start=1):
        rec = item.recommendation
        isin_val = next(
            (a.isin for a in assets if (a.yahoo_ticker == item.symbol or a.isin == item.symbol)), ""
        )
        curr_pct = f"{current_allocations.get(isin_val, 0.0):.1f}%"
        tgt_pct = f"{rec.target_allocation_pct:.1f}%"
        md.append(
            f"| #{rank} | **{item.name}** | `{item.symbol}` | {item.asset_type} | "
            f"{curr_pct} | {tgt_pct} | `{item.final_score:.4f}` | "
            f"**{rec.action.value}** | {rec.confidence_score * 100:.0f}% |"
        )

    md.extend(
        [
            "",
            "---",
            "",
            "## 4. Quantitative Score Decomposition",
            "",
            "| Symbol | Final Score | Penalty Factor | Dip Score | Cost / P/E Score | Allocation Gap Score | 52w Range Score |",
            "|---|---|---|---|---|---|---|",
        ]
    )

    for item in scored_assets:
        md.append(
            f"| `{item.symbol}` | **`{item.final_score:.4f}`** | `{item.penalty_factor:.2f}` | "
            f"`{item.dip_score:.4f}` | `{item.cost_or_pe_score:.4f}` | "
            f"`{item.allocation_score:.4f}` | `{item.range_score:.4f}` |"
        )

    md.extend(
        [
            "",
            "---",
            "",
            "## 5. Decision Rationale & Rebalance Findings",
            "",
        ]
    )

    for item in scored_assets:
        rec = item.recommendation
        md.append(f"### #{item.name} (`{item.symbol}`)")
        md.append(
            f"- **Recommended Action:** **{rec.action.value}** (Urgency: {rec.urgency_level.value}, Confidence: {rec.confidence_score * 100:.0f}%)"
        )
        md.append(
            f"- **Quality Tier:** {item.quality_tier} | **Valuation Status:** {item.valuation_status}"
        )
        md.append(f"- **Rationale:** {rec.reasoning}")
        md.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    logger.success(f"[run analysis] Analysis report successfully written to '{output_path}'.")


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

    # Load all 17 portfolio assets (10 active holdings + 7 watchlist items)
    assets = portfolio_repo.load_all_assets()
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

    sector_pcts, country_pcts = exposure_engine.calculate_consolidated_exposure(latest_snapshot)
    penalties_map = _calculate_exposure_penalties(
        sector_pcts=sector_pcts,
        country_pcts=country_pcts,
        snapshot=latest_snapshot,
        settings=settings,
    )

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
            eval_res = evaluate_stock_quality(stock_details)
            quality_tier = str(eval_res["tier"])
            val_status = str(eval_res.get("valuation_status", "Fair Value"))

            with get_db_context(str(db_path)) as conn:
                cur_t = conn.cursor()
                cur_t.execute(
                    "SELECT id FROM assets WHERE isin = ?",
                    (isin,),
                )
                row_asset = cur_t.fetchone()
                asset_id_val = int(row_asset["id"]) if row_asset else None

                if asset_id_val is not None:
                    opp_repo.upsert_asset_fundamentals(
                        asset_id=asset_id_val,
                        asset_type="STOCK",
                        details=stock_details,
                        quality_tier=quality_tier,
                        quality_score=int(eval_res.get("score", 0)),
                    )

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
            aum_eur = (
                (etf_details.fund_size_eur_m or 0.0) * 1_000_000.0
                if etf_details.fund_size_eur_m
                else None
            )
            # Calculate fund age for consistent tier evaluation
            age_years: float | None = None
            if etf_details.inception_date:
                from scripts.run_quality import _calculate_age_years

                age_years = _calculate_age_years(etf_details.inception_date)

            etf_eval = evaluate_etf_quality(etf_details, aum_eur=aum_eur, age_years=age_years)
            quality_tier = str(etf_eval["tier"])
            val_status = str(etf_eval.get("valuation_status", "Fair Value"))

            with get_db_context(str(db_path)) as conn:
                cur_t = conn.cursor()
                cur_t.execute(
                    "SELECT id FROM assets WHERE isin = ?",
                    (isin,),
                )
                row_asset = cur_t.fetchone()
                asset_id_val = int(row_asset["id"]) if row_asset else None

                if asset_id_val is not None:
                    opp_repo.upsert_asset_fundamentals(
                        asset_id=asset_id_val,
                        asset_type="ETF",
                        details=etf_details,
                        quality_tier=quality_tier,
                        quality_score=int(etf_eval.get("score", 0)),
                    )
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

    # Generate Markdown Report in reports/analysis_report.md
    report_file = REPORTS_DIR / "analysis_report.md"
    _generate_markdown_analysis_report(
        snapshot=latest_snapshot,
        scored_assets=scored_assets,
        assets=assets,
        sector_pcts=sector_pcts,
        country_pcts=country_pcts,
        penalties_map=penalties_map,
        current_allocations=current_allocations,
        targets_map=targets_map,
        output_path=report_file,
    )

    logger.success("[run analysis] Opportunity analysis pipeline executed successfully.")


if __name__ == "__main__":
    main()
