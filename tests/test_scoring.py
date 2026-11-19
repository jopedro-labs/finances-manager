"""Unit tests for the deterministic scoring engine."""

from __future__ import annotations

import pytest

from config import Settings
from core.models import Asset, ETFDetails, RecommendationAction, StockDetails
from core.scoring import (
    apply_exposure_penalty,
    build_recommendation,
    calculate_52w_range_score,
    calculate_allocation_gap_score,
    calculate_dip_score,
    calculate_pe_growth_score,
    calculate_ter_score,
    score_etf,
    score_stock,
)


@pytest.fixture
def settings() -> Settings:
    return Settings()


def test_calculate_dip_score(settings: Settings) -> None:
    # 1. No dip (< 5%)
    assert calculate_dip_score(98.0, 100.0, settings) < 0.20
    # 2. Healthy dip (15% is sweet spot between 5% and 20%)
    score_15 = calculate_dip_score(85.0, 100.0, settings)
    assert 0.70 <= score_15 <= 1.0
    # 3. Maximum sweet spot at 20%
    score_20 = calculate_dip_score(80.0, 100.0, settings)
    assert score_20 == 1.0
    # 4. Falling knife (> 20%)
    score_falling = calculate_dip_score(50.0, 100.0, settings)
    assert score_falling < 0.50
    # 5. Invalid prices
    assert calculate_dip_score(None, 100.0, settings) == 0.0
    assert calculate_dip_score(110.0, 100.0, settings) == 0.0


def test_calculate_pe_growth_score(settings: Settings) -> None:
    # 1. Earnings expansion (forward_pe < trailing_pe)
    assert calculate_pe_growth_score(15.0, 25.0, settings) > settings.pe_neutral_score
    # 2. Earnings contraction (forward_pe > trailing_pe)
    assert calculate_pe_growth_score(30.0, 20.0, settings) < settings.pe_neutral_score
    # 3. Missing data defaults to neutral
    assert calculate_pe_growth_score(None, 20.0, settings) == settings.pe_neutral_score


def test_calculate_52w_range_score(settings: Settings) -> None:
    # Bottom band (<= 30% of range)
    assert calculate_52w_range_score(120.0, 100.0, 200.0, settings) == 1.0
    # Top of range
    assert calculate_52w_range_score(200.0, 100.0, 200.0, settings) == 0.0
    # Invalid range
    assert calculate_52w_range_score(150.0, 200.0, 100.0, settings) == 0.5


def test_calculate_ter_score(settings: Settings) -> None:
    # Excellent TER (<= 0.10%)
    assert calculate_ter_score(0.07, settings) == 1.0
    # Poor TER (>= 0.50%)
    assert calculate_ter_score(0.55, settings) == 0.0
    # Intermediate TER
    assert 0.40 <= calculate_ter_score(0.25, settings) <= 0.70
    # Missing
    assert calculate_ter_score(None, settings) == 0.50


def test_calculate_allocation_gap_score(settings: Settings) -> None:
    # Under-allocated
    assert calculate_allocation_gap_score(5.0, 20.0, settings) == 1.0
    # Over-allocated
    assert calculate_allocation_gap_score(15.0, 10.0, settings) == 0.0


def test_apply_exposure_penalty() -> None:
    assert apply_exposure_penalty(0.80, 1.0) == 0.80
    assert apply_exposure_penalty(0.80, 0.50) == 0.40
    assert apply_exposure_penalty(0.80, -0.5) == 0.0


def test_build_recommendation_matrix() -> None:
    # Tier A + Undervalued + Under-allocated => BUY
    rec1 = build_recommendation("Tier A", "Undervalued", 0.85, 5.0, 10.0)
    assert rec1.action == RecommendationAction.BUY
    assert rec1.confidence_score == 1.0

    # Tier A + Overvalued + Under-allocated => BUY (Fractional)
    rec2 = build_recommendation("Tier A", "Overvalued", 0.65, 3.0, 10.0)
    assert rec2.action == RecommendationAction.BUY
    assert rec2.confidence_score == 0.60

    # Tier A + Fair Value + Over-allocated => HOLD
    rec3 = build_recommendation("Tier A", "Fair Value", 0.50, -2.0, 10.0)
    assert rec3.action == RecommendationAction.HOLD

    # Tier B + Overvalued + Over-allocated => HOLD/REBAL
    rec4 = build_recommendation("Tier B", "Overvalued", 0.40, -3.0, 5.0)
    assert rec4.action == RecommendationAction.HOLD_REBALANCE

    # Tier C + Overvalued => SELL
    rec5 = build_recommendation("Tier C", "Overvalued", 0.20, 0.0, 0.0)
    assert rec5.action == RecommendationAction.SELL
    assert rec5.confidence_score == 1.0


def test_score_stock_end_to_end(settings: Settings) -> None:
    asset = Asset(
        name="NVIDIA Corporation",
        yahoo_ticker="NVDA",
        isin="US67066G1040",
        asset_type="STOCK",
        quantity=10.0,
        average_buy_price=100.0,
    )
    details = StockDetails(
        pe_ratio=30.0,
        forward_pe=20.0,
        fifty_two_week_high=150.0,
        fifty_two_week_low=80.0,
    )
    scored = score_stock(
        asset=asset,
        details=details,
        current_alloc_pct=2.0,
        target_alloc_pct=5.0,
        current_price=125.0,
        quality_tier="Tier A",
        valuation_status="Fair Value",
        penalty_factor=1.0,
        settings=settings,
    )
    assert scored.symbol == "NVDA"
    assert scored.asset_type == "STOCK"
    assert scored.final_score > 0.50
    assert scored.recommendation.action == RecommendationAction.BUY


def test_score_etf_end_to_end(settings: Settings) -> None:
    asset = Asset(
        name="Core MSCI World",
        yahoo_ticker="EUNL.DE",
        isin="IE00B4L5Y983",
        asset_type="ETF",
        quantity=50.0,
        average_buy_price=80.0,
    )
    details = ETFDetails(
        holdings=[],
        sector_breakdown=[],
        country_breakdown=[],
        ter_pct=0.20,
    )
    scored = score_etf(
        asset=asset,
        details=details,
        current_alloc_pct=15.0,
        target_alloc_pct=26.0,
        current_price=95.0,
        peak_price=100.0,
        quality_tier="Tier A",
        valuation_status="Fair Value",
        penalty_factor=0.90,  # 10% penalty
        settings=settings,
    )
    assert scored.symbol == "EUNL.DE"
    assert scored.asset_type == "ETF"
    assert scored.penalty_factor == 0.90
    assert scored.final_score == round(scored.raw_score * 0.90, 4)
    assert scored.recommendation.action == RecommendationAction.BUY
