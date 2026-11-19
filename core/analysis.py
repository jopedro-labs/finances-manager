"""This file contains functions for analyzing portfolio performance, asset
exposures, and deterministic fundamental quality tier evaluations using Pandas
vectorization.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from core_lib.logger import logger

from core.data_collectors import ETFProvider, StockProvider
from core.exceptions import StorageError
from core.exposure import ExposureEngine
from core.models import Asset, ETFDetails, PortfolioSnapshot, StockDetails
from core.repositories import (
    HistoryRepository,
    PortfolioRepository,
    SqliteHistoryRepository,
    SqlitePortfolioRepository,
)
from infra.database.connection import DEFAULT_DB_PATH


@dataclass
class PortfolioExposure:
    """Aggregated portfolio exposure across sectors and countries."""

    sector_exposure: dict[str, float] = field(default_factory=dict)
    country_exposure: dict[str, float] = field(default_factory=dict)
    total_etf_value_eur: float = 0.0


def calculate_portfolio_exposure(
    snapshot: PortfolioSnapshot,
    portfolio_repo: PortfolioRepository | None = None,
    etf_provider: ETFProvider | None = None,
    stock_provider: StockProvider | None = None,
) -> PortfolioExposure:
    """Calculates consolidated value-weighted sector and country exposure.

    .. deprecated::
        Use :meth:`ExposureEngine.calculate_consolidated_exposure` instead.
        This wrapper will be removed in a future release.

    Args:
        snapshot: PortfolioSnapshot containing current holdings and valuations.
        portfolio_repo: Optional portfolio repository override.
        etf_provider: Optional ETF data provider override.
        stock_provider: Optional stock data provider override.

    Returns:
        A PortfolioExposure instance with sector and country percentage dicts.
    """
    warnings.warn(
        "[analysis] calculate_portfolio_exposure is deprecated; "
        "use ExposureEngine.calculate_consolidated_exposure() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    engine: ExposureEngine = ExposureEngine(
        etf_provider=etf_provider,
        stock_provider=stock_provider,
        portfolio_repo=portfolio_repo,
    )
    sector_pcts: dict[str, float]
    country_pcts: dict[str, float]
    sector_pcts, country_pcts = engine.calculate_consolidated_exposure(snapshot)
    return PortfolioExposure(
        sector_exposure=sector_pcts,
        country_exposure=country_pcts,
    )


def analyze_overall_performance(
    portfolio_repo: PortfolioRepository | None = None,
    history_repo: HistoryRepository | None = None,
) -> None:
    """Logs per-asset and global portfolio performance using the latest snapshot.

    Loads all configured assets and the full snapshot history, then prints
    acquisition cost, latest market value, absolute gain/loss, and overall ROI
    to the terminal via the structured logger. Silently returns if history is
    empty or storage cannot be read.

    Args:
        portfolio_repo: Repository for loading current assets. Defaults to
            SqlitePortfolioRepository backed by DEFAULT_DB_PATH.
        history_repo: Repository for loading snapshot history. Defaults to
            SqliteHistoryRepository backed by DEFAULT_DB_PATH.
    """
    logger.section("[analysis] Portfolio Performance Analysis")

    p_repo: PortfolioRepository = portfolio_repo or SqlitePortfolioRepository(DEFAULT_DB_PATH)
    h_repo: HistoryRepository = history_repo or SqliteHistoryRepository(DEFAULT_DB_PATH)

    try:
        assets: list[Asset] = p_repo.load_assets()
        history: list[PortfolioSnapshot] = h_repo.load_history()

        if not history:
            logger.warning("[analysis] History storage is empty. Cannot perform analysis.")
            return

        latest_snapshot: PortfolioSnapshot = history[-1]
    except StorageError as e:
        logger.error(f"[analysis] Could not read data from storage: {e}")
        return

    latest_asset_values: dict[str, float] = {
        asset.isin: asset.market_value_eur
        for asset in latest_snapshot.assets_snapshot
        if asset.isin
    }

    performance_records: list[dict[str, Any]] = []

    for asset in assets:
        acquisition_cost: float = asset.acquisition_cost
        latest_value: float | None = latest_asset_values.get(asset.isin) if asset.isin else None

        if latest_value is None:
            logger.warning(f"[analysis] No recent market data found for {asset.name}. Skipping.")
            continue

        performance_records.append(
            {
                "name": asset.name,
                "acquisition_cost": acquisition_cost,
                "latest_value": latest_value,
                "absolute_gain": latest_value - acquisition_cost,
            }
        )

    if not performance_records:
        logger.warning("[analysis] No valid asset performance records found.")
        return

    for record in performance_records:
        name: str = str(record["name"])
        acq_cost: float = float(record["acquisition_cost"])
        lat_val: float = float(record["latest_value"])
        abs_gain: float = float(record["absolute_gain"])

        logger.subsection(name)
        logger.info(f"[analysis] Acquisition Cost: {acq_cost:.2f} EUR")
        logger.info(f"[analysis] Latest Market Value: {lat_val:.2f} EUR")

        if abs_gain >= 0:
            logger.success(f"[analysis] Absolute Gain: +{abs_gain:.2f} EUR")
        else:
            logger.warning(f"[analysis] Absolute Loss: {abs_gain:.2f} EUR")

    logger.section("[analysis] Global Analysis")

    df_perf: pd.DataFrame = pd.DataFrame(performance_records)
    total_acquisition_cost: float = float(df_perf["acquisition_cost"].sum())
    total_latest_value: float = float(df_perf["latest_value"].sum())
    total_absolute_gain: float = float(df_perf["absolute_gain"].sum())

    logger.info(f"[analysis] Total Acquisition Cost: {total_acquisition_cost:.2f} EUR")
    logger.info(f"[analysis] Latest Market Value:   {total_latest_value:.2f} EUR")

    if total_absolute_gain >= 0:
        logger.success(f"[analysis] Absolute Gain: +{total_absolute_gain:.2f} EUR")
    else:
        logger.warning(f"[analysis] Absolute Loss: {total_absolute_gain:.2f} EUR")

    roi_percentage: float = (
        (total_absolute_gain / total_acquisition_cost) * 100.0
        if total_acquisition_cost != 0.0
        else 0.0
    )

    if roi_percentage >= 0:
        logger.success(f"[analysis] Return on Investment (ROI): +{roi_percentage:.2f}%")
    else:
        logger.warning(f"[analysis] Return on Investment (ROI): {roi_percentage:.2f}%")


def evaluate_stock_quality(details: StockDetails) -> dict[str, Any]:
    """Evaluates stock fundamental health and classifies it into a quality tier.

    Scores the stock 0–100 across four dimensions (operating margin, revenue
    growth, debt-to-equity, earnings growth), then applies knockout rules to
    force Tier C for critically unhealthy fundamentals, and promotes to Tier A
    only when the score and key metrics all pass the top-tier thresholds.

    Args:
        details: StockDetails instance containing the fundamental metrics to evaluate.

    Returns:
        A dict with keys:
        - ``score`` (int): Raw score 0–100.
        - ``max_score`` (int): Always 100.
        - ``tier`` (str): 'Tier A', 'Tier B', or 'Tier C'.
        - ``bull_case`` (list[str]): Positive fundamental observations.
        - ``bear_case`` (list[str]): Risk or weakness observations.
        - ``valuation_status`` (str): 'Undervalued', 'Fair Value', or 'Overvalued'.
    """
    score: int = 0
    max_score: int = 100

    # 1. Operating Margin (25 pts max)
    margin: float | None = details.profit_margins_pct
    if margin is not None:
        if margin >= 20.0:
            score += 25
        elif margin >= 10.0:
            score += 15

    # 2. Revenue Growth YoY (25 pts max)
    rev_growth: float | None = details.revenue_growth_pct
    if rev_growth is not None:
        if rev_growth >= 8.0:
            score += 25
        elif rev_growth >= 3.0:
            score += 15

    # 3. Balance Sheet Health - Debt to Equity (25 pts max)
    debt_eq: float | None = details.total_debt_to_equity
    normalized_de: float | None = None
    if debt_eq is not None:
        normalized_de = debt_eq / 100.0 if debt_eq > 10.0 else debt_eq
        if normalized_de <= 1.0:
            score += 25
        elif normalized_de <= 2.0:
            score += 15
    else:
        score += 12

    # 4. Earnings Growth (25 pts max)
    earn_growth: float | None = details.earnings_growth_pct
    if earn_growth is not None:
        if earn_growth >= 10.0:
            score += 25
        elif earn_growth >= 5.0:
            score += 15

    # --- Knockout Rules & Tier Assignment ---
    tier: str = "Tier B"
    is_knockout_c: bool = False

    if margin is not None and margin < 0.0 or debt_eq is not None and debt_eq > 250.0:
        is_knockout_c = True

    if is_knockout_c:
        tier = "Tier C"
    else:
        de_val: float = debt_eq if debt_eq is not None else 0.0
        margin_val: float = margin if margin is not None else 0.0
        if score >= 80 and margin_val > 10.0 and de_val <= 150.0:
            tier = "Tier A"
        elif score >= 50:
            tier = "Tier B"
        else:
            tier = "Tier C"

    # --- Diagnostic Bull & Bear Cases ---
    bull_points: list[str] = []
    bear_points: list[str] = []

    if margin is not None and margin >= 15.0:
        bull_points.append(f"Strong operating profit margins ({margin:.1f}%)")
    else:
        bear_points.append("Compressed or subdued operating margins")

    if rev_growth is not None and rev_growth >= 5.0:
        bull_points.append(f"Healthy revenue expansion ({rev_growth:.1f}% YoY)")
    else:
        bear_points.append("Slow or stagnant top-line revenue growth")

    if debt_eq is not None:
        pct_de = debt_eq if debt_eq > 5.0 else debt_eq * 100.0
        if pct_de <= 80.0:
            bull_points.append(
                f"Conservative capital structure and low leverage (D/E: {pct_de:.1f}%)"
            )
        elif pct_de <= 150.0:
            bull_points.append(
                f"Moderate leverage aligned with industry averages (D/E: {pct_de:.1f}%)"
            )
        else:
            bear_points.append(f"Elevated debt-to-equity leverage ratio (D/E: {pct_de:.1f}%)")
    else:
        bear_points.append("Debt and leverage metrics unavailable")

    if not bull_points:
        bull_points.append("Established business model with stable market presence")
    if not bear_points:
        bear_points.append("No critical balance sheet vulnerabilities detected")

    # --- Valuation Status ---
    valuation_status: str = "Fair Value"
    pe: float | None = details.pe_ratio
    if pe is not None:
        if pe < 15.0:
            valuation_status = "Undervalued"
        elif pe > 30.0:
            valuation_status = "Overvalued"
        else:
            valuation_status = "Fair Value"

    return {
        "score": score,
        "max_score": max_score,
        "tier": tier,
        "bull_case": bull_points,
        "bear_case": bear_points,
        "valuation_status": valuation_status,
    }


def evaluate_etf_quality(
    details: ETFDetails,
    aum_eur: float | None = None,
    age_years: float | None = None,
) -> dict[str, Any]:
    """Classifies ETF quality into a tier based on cost, fund size, and maturity.

    Tier A requires TER ≤ 0.20%, AUM > 500M€, and fund age > 3 years — all
    conditions that are present must pass. Tier C is triggered by TER > 0.45%
    or AUM < 100M€. Otherwise Tier B.

    Args:
        details: ETFDetails instance containing TER and composition metadata.
        aum_eur: Assets Under Management in EUR. If None, this dimension is skipped.
        age_years: Fund age in years since inception. If None, this dimension is skipped.

    Returns:
        A dict with keys:
        - ``score`` (int): 100 for Tier A, 70 for Tier B, 40 for Tier C.
        - ``max_score`` (int): Always 100.
        - ``tier`` (str): 'Tier A', 'Tier B', or 'Tier C'.
        - ``bull_case`` (list[str]): Cost and scale observations.
        - ``bear_case`` (list[str]): Structural risk observations.
        - ``valuation_status`` (str): Always 'Fair Value' for ETFs.
    """
    ter: float | None = details.ter_pct
    tier: str = "Tier B"

    is_tier_a: bool = True
    if ter is not None and ter > 0.20:
        is_tier_a = False
    if aum_eur is not None and aum_eur <= 500_000_000.0:
        is_tier_a = False
    if age_years is not None and age_years <= 5.0:
        is_tier_a = False

    if is_tier_a and (ter is not None or aum_eur is not None or age_years is not None):
        tier = "Tier A"
    else:
        is_tier_c: bool = False
        if ter is not None and ter > 0.45:
            is_tier_c = True
        if aum_eur is not None and aum_eur < 100_000_000.0:
            is_tier_c = True

        tier = "Tier C" if is_tier_c else "Tier B"

    ter_str: str = f"{ter:.2f}%" if ter is not None else "N/A"
    aum_str: str = f"{aum_eur / 1e6:,.1f}M€" if aum_eur is not None else "N/A"

    bull_points: list[str] = []
    bear_points: list[str] = []

    if ter is not None and ter <= 0.25:
        bull_points.append(f"Attractive cost efficiency (TER: {ter_str})")
    elif ter is not None and ter > 0.45:
        bear_points.append(f"Elevated fund total expense ratio (TER: {ter_str})")
    else:
        bull_points.append(f"Balanced cost structure (TER: {ter_str})")

    if aum_eur is not None and aum_eur >= 500_000_000.0:
        bull_points.append(f"High fund scale and deep liquidity (AUM: {aum_str})")
    elif aum_eur is not None and aum_eur < 100_000_000.0:
        bear_points.append(f"Small fund scale / closure risk (AUM: {aum_str})")
    else:
        bull_points.append(f"Adequate fund scale and liquidity (AUM: {aum_str})")

    bear_points.append("Market systemic exposure without individual stock selection")

    return {
        "score": 100 if tier == "Tier A" else (70 if tier == "Tier B" else 40),
        "max_score": 100,
        "tier": tier,
        "bull_case": bull_points,
        "bear_case": bear_points,
        "valuation_status": "Fair Value",
    }
