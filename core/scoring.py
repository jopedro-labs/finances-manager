"""Deterministic quantitative scoring and recommendation engine.

Implements pure mathematical scoring formulas and the qualitative decision matrix
defined in data/rules.md, operating offline without LLM dependencies.
"""

from __future__ import annotations

from config import Settings, get_settings
from core.models import (
    Asset,
    ETFDetails,
    RebalanceRecommendation,
    RecommendationAction,
    ScoredAsset,
    StockDetails,
    UrgencyLevel,
)


def calculate_dip_score(
    current_price: float | None,
    peak_price: float | None,
    settings: Settings | None = None,
) -> float:
    """Calculates technical dip discount score using a trapezoidal curve.

    Penalizes uncontrolled drops (> dip_max_pct, falling knives) while rewarding
    healthy technical discounts between dip_min_pct and dip_max_pct.

    Args:
        current_price: Current market price.
        peak_price: Recent high or 52-week high price.
        settings: Application settings override.

    Returns:
        Normalized dip score between 0.0 and 1.0.
    """
    if not current_price or not peak_price or peak_price <= 0.0 or current_price > peak_price:
        return 0.0

    cfg = settings or get_settings()
    discount_pct = ((peak_price - current_price) / peak_price) * 100.0

    if discount_pct < cfg.dip_min_pct:
        return round(max(0.0, discount_pct / cfg.dip_min_pct * 0.4), 4)
    elif discount_pct <= cfg.dip_max_pct:
        # Sweet spot: linear scale from 0.5 to 1.0
        span = cfg.dip_max_pct - cfg.dip_min_pct
        ratio = (discount_pct - cfg.dip_min_pct) / span if span > 0 else 1.0
        return round(0.5 + 0.5 * ratio, 4)
    else:
        # Falling knife penalty: degrades as discount exceeds dip_max_pct
        excess = discount_pct - cfg.dip_max_pct
        penalty = min(0.8, (excess / 30.0) * 0.8)
        return round(max(0.1, 1.0 - penalty), 4)


def calculate_pe_growth_score(
    forward_pe: float | None,
    trailing_pe: float | None,
    settings: Settings | None = None,
) -> float:
    """Calculates valuation multiplier score favoring companies with earnings growth.

    Args:
        forward_pe: Projected forward P/E multiple.
        trailing_pe: Trailing twelve-month P/E multiple.
        settings: Application settings override.

    Returns:
        Score between 0.0 and 1.0.
    """
    cfg = settings or get_settings()
    if not forward_pe or forward_pe <= 0.0:
        return cfg.pe_neutral_score

    if not trailing_pe or trailing_pe <= 0.0:
        return cfg.pe_neutral_score

    if forward_pe < trailing_pe:
        # Earnings acceleration: forward multiple is lower than trailing
        expansion = (trailing_pe - forward_pe) / trailing_pe
        bonus = min(0.4, expansion * cfg.pe_growth_multiplier)
        return round(min(1.0, cfg.pe_neutral_score + bonus), 4)
    else:
        # Earnings compression
        contraction = (forward_pe - trailing_pe) / trailing_pe
        penalty = min(0.4, contraction * 1.5)
        return round(max(0.1, cfg.pe_neutral_score - penalty), 4)


def calculate_52w_range_score(
    current_price: float | None,
    low_52w: float | None,
    high_52w: float | None,
    settings: Settings | None = None,
) -> float:
    """Calculates positioning score within 52-week low/high trading channel.

    Prices positioned near bottom range (< range_bottom_band) receive maximum scores.

    Args:
        current_price: Current market quotation.
        low_52w: 52-week low quotation.
        high_52w: 52-week high quotation.
        settings: Application settings override.

    Returns:
        Score between 0.0 and 1.0.
    """
    if not current_price or not low_52w or not high_52w or high_52w <= low_52w:
        return 0.5

    cfg = settings or get_settings()
    position = (current_price - low_52w) / (high_52w - low_52w)
    position = max(0.0, min(1.0, position))

    if position <= cfg.range_bottom_band:
        return 1.0
    return round(
        max(0.0, 1.0 - ((position - cfg.range_bottom_band) / (1.0 - cfg.range_bottom_band))), 4
    )


def calculate_ter_score(
    ter_pct: float | None,
    settings: Settings | None = None,
) -> float:
    """Calculates cost efficiency score for ETFs based on Total Expense Ratio.

    Args:
        ter_pct: Total Expense Ratio in percentage (e.g., 0.20 for 0.20%).
        settings: Application settings override.

    Returns:
        Score between 0.0 and 1.0.
    """
    if ter_pct is None or ter_pct < 0.0:
        return 0.5

    cfg = settings or get_settings()
    if ter_pct <= cfg.ter_low_pct:
        return 1.0
    if ter_pct >= cfg.ter_high_pct:
        return 0.0

    span = cfg.ter_high_pct - cfg.ter_low_pct
    return round(1.0 - ((ter_pct - cfg.ter_low_pct) / span), 4)


def calculate_allocation_gap_score(
    current_alloc_pct: float,
    target_alloc_pct: float,
    settings: Settings | None = None,
) -> float:
    """Calculates rebalancing allocation gap score favoring under-allocated assets.

    Args:
        current_alloc_pct: Current portfolio weight percentage.
        target_alloc_pct: Target strategic weight percentage.
        settings: Application settings override.

    Returns:
        Score between 0.0 and 1.0.
    """
    cfg = settings or get_settings()
    gap = target_alloc_pct - current_alloc_pct

    if gap <= 0.0:
        # Asset is at or above target weight
        return 0.0

    normalizer = cfg.alloc_gap_normalizer_pct if target_alloc_pct >= 10.0 else cfg.alloc_gap_max_pct
    return round(min(1.0, gap / normalizer), 4)


def apply_exposure_penalty(score: float, penalty_factor: float) -> float:
    """Applies concentration penalty factor to raw quantitative score.

    Args:
        score: Raw unpenalized score (0.0 to 1.0).
        penalty_factor: Penalty multiplier (1.0 = no penalty, < 1.0 = penalized).

    Returns:
        Penalized final score between 0.0 and 1.0.
    """
    clamped_penalty = max(0.0, min(1.0, penalty_factor))
    return round(max(0.0, min(1.0, score * clamped_penalty)), 4)


def build_recommendation(
    tier: str,
    valuation_status: str,
    score: float,
    alloc_gap_pct: float,
    target_alloc_pct: float,
) -> RebalanceRecommendation:
    """Builds qualitative rebalance recommendation matching rules.md Decision Matrix.

    Args:
        tier: Quality tier ('Tier A', 'Tier B', 'Tier C').
        valuation_status: Valuation string ('Undervalued', 'Fair Value', 'Overvalued').
        score: Quantitative final score (0.0 to 1.0).
        alloc_gap_pct: Target allocation minus current allocation percentage.
        target_alloc_pct: Target allocation percentage.

    Returns:
        RebalanceRecommendation instance.
    """
    norm_tier = tier.upper()
    norm_val = valuation_status.upper()
    under_allocated = alloc_gap_pct > 0.5

    # Decision Matrix from rules.md Section 2
    if "TIER A" in norm_tier:
        if "OVERVALUED" in norm_val:
            if under_allocated:
                action = RecommendationAction.BUY
                confidence = 0.60
                urgency = UrgencyLevel.LOW
                reason = "Tier A quality asset with stretched valuation; recommend fractional accumulation."
            else:
                action = RecommendationAction.HOLD
                confidence = 0.80
                urgency = UrgencyLevel.LOW
                reason = "Tier A quality at target weight; maintain position."
        else:  # Undervalued or Fair Value
            if under_allocated:
                action = RecommendationAction.BUY
                confidence = 1.0
                urgency = UrgencyLevel.HIGH if score > 0.70 else UrgencyLevel.MEDIUM
                reason = f"Tier A quality ({norm_val.title()}) under target weight by {alloc_gap_pct:.1f}%."
            else:
                action = RecommendationAction.HOLD
                confidence = 0.80
                urgency = UrgencyLevel.LOW
                reason = "Tier A quality asset currently at or above target weight."

    elif "TIER B" in norm_tier:
        if "UNDERVALUED" in norm_val and under_allocated:
            action = RecommendationAction.BUY
            confidence = 0.60
            urgency = UrgencyLevel.MEDIUM
            reason = f"Tier B solid asset trading undervalued; opportunistic rebalance of +{alloc_gap_pct:.1f}%."
        elif "OVERVALUED" in norm_val and not under_allocated:
            action = RecommendationAction.HOLD_REBALANCE
            confidence = 0.80
            urgency = UrgencyLevel.MEDIUM
            reason = "Tier B asset overvalued and overweight; trim excess capital."
        else:
            action = RecommendationAction.HOLD
            confidence = 0.60
            urgency = UrgencyLevel.LOW
            reason = "Tier B stable asset within acceptable allocation bounds."

    else:  # Tier C
        if "OVERVALUED" in norm_val or not under_allocated:
            action = RecommendationAction.SELL
            confidence = 1.0
            urgency = UrgencyLevel.HIGH
            reason = "Tier C speculative asset overvalued or overweight; liquidate position."
        else:
            action = RecommendationAction.HOLD_REBALANCE
            confidence = 0.60
            urgency = UrgencyLevel.MEDIUM
            reason = "Tier C holding with fundamental weaknesses; rebalance capital to Tier A core."

    return RebalanceRecommendation(
        action=action,
        confidence_score=confidence,
        reasoning=reason[:250],
        target_allocation_pct=max(0.0, min(100.0, target_alloc_pct)),
        urgency_level=urgency,
        risk_score=2 if "TIER A" in norm_tier else (3 if "TIER B" in norm_tier else 5),
        valuation_score=8 if "UNDERVALUED" in norm_val else (6 if "FAIR VALUE" in norm_val else 3),
    )


def score_stock(
    asset: Asset,
    details: StockDetails,
    current_alloc_pct: float,
    target_alloc_pct: float,
    current_price: float | None = None,
    quality_tier: str = "Tier B",
    valuation_status: str = "Fair Value",
    penalty_factor: float = 1.0,
    settings: Settings | None = None,
) -> ScoredAsset:
    """Computes complete quantitative score and recommendation for a stock asset.

    Args:
        asset: Domain Asset instance.
        details: Fundamental metrics and ratios.
        current_alloc_pct: Current portfolio allocation percentage.
        target_alloc_pct: Target strategic allocation percentage.
        current_price: Current market quotation in EUR.
        quality_tier: Evaluated fundamental tier (e.g., 'Tier A').
        valuation_status: Valuation category ('Undervalued', 'Fair Value', 'Overvalued').
        penalty_factor: Concentration limit penalty multiplier (0.0 to 1.0).
        settings: Application settings override.

    Returns:
        ScoredAsset instance.
    """
    cfg = settings or get_settings()
    high_52w = details.fifty_two_week_high
    low_52w = details.fifty_two_week_low

    dip = calculate_dip_score(current_price, high_52w, settings=cfg)
    pe = calculate_pe_growth_score(details.forward_pe, details.pe_ratio, settings=cfg)
    range_pos = calculate_52w_range_score(current_price, low_52w, high_52w, settings=cfg)
    alloc = calculate_allocation_gap_score(current_alloc_pct, target_alloc_pct, settings=cfg)

    raw_score = (
        cfg.stock_weight_dip * dip
        + cfg.stock_weight_forward_pe * pe
        + cfg.stock_weight_52w_range * range_pos
        + cfg.stock_weight_allocation * alloc
    )
    rounded_raw = round(raw_score, 4)
    final_score = apply_exposure_penalty(rounded_raw, penalty_factor)

    alloc_gap = target_alloc_pct - current_alloc_pct
    recommendation = build_recommendation(
        tier=quality_tier,
        valuation_status=valuation_status,
        score=final_score,
        alloc_gap_pct=alloc_gap,
        target_alloc_pct=target_alloc_pct,
    )

    return ScoredAsset(
        symbol=asset.yahoo_ticker or asset.isin or asset.name,
        name=asset.name,
        asset_type="STOCK",
        raw_score=rounded_raw,
        penalty_factor=round(penalty_factor, 4),
        final_score=round(final_score, 4),
        quality_tier=quality_tier,
        valuation_status=valuation_status,
        recommendation=recommendation,
        dip_score=dip,
        cost_or_pe_score=pe,
        allocation_score=alloc,
        range_score=range_pos,
    )


def score_etf(
    asset: Asset,
    details: ETFDetails,
    current_alloc_pct: float,
    target_alloc_pct: float,
    current_price: float | None = None,
    peak_price: float | None = None,
    quality_tier: str = "Tier A",
    valuation_status: str = "Fair Value",
    penalty_factor: float = 1.0,
    settings: Settings | None = None,
) -> ScoredAsset:
    """Computes complete quantitative score and recommendation for an ETF asset.

    Args:
        asset: Domain Asset instance.
        details: ETF composition and TER details.
        current_alloc_pct: Current portfolio allocation percentage.
        target_alloc_pct: Target strategic allocation percentage.
        current_price: Current market quotation in EUR.
        peak_price: Recent high price if available.
        quality_tier: Evaluated fundamental tier.
        valuation_status: Valuation category.
        penalty_factor: Concentration limit penalty multiplier (0.0 to 1.0).
        settings: Application settings override.

    Returns:
        ScoredAsset instance.
    """
    cfg = settings or get_settings()

    dip = calculate_dip_score(current_price, peak_price, settings=cfg)
    ter = calculate_ter_score(details.ter_pct, settings=cfg)
    alloc = calculate_allocation_gap_score(current_alloc_pct, target_alloc_pct, settings=cfg)

    raw_score = (
        cfg.etf_weight_dip * dip + cfg.etf_weight_ter * ter + cfg.etf_weight_allocation * alloc
    )
    rounded_raw = round(raw_score, 4)
    final_score = apply_exposure_penalty(rounded_raw, penalty_factor)

    alloc_gap = target_alloc_pct - current_alloc_pct
    recommendation = build_recommendation(
        tier=quality_tier,
        valuation_status=valuation_status,
        score=final_score,
        alloc_gap_pct=alloc_gap,
        target_alloc_pct=target_alloc_pct,
    )

    return ScoredAsset(
        symbol=asset.yahoo_ticker or asset.isin or asset.name,
        name=asset.name,
        asset_type="ETF",
        raw_score=rounded_raw,
        penalty_factor=round(penalty_factor, 4),
        final_score=round(final_score, 4),
        quality_tier=quality_tier,
        valuation_status=valuation_status,
        recommendation=recommendation,
        dip_score=dip,
        cost_or_pe_score=ter,
        allocation_score=alloc,
        range_score=0.0,
    )
