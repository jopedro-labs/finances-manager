"""
Domain models and structured data schemas for the personal finances application.
Provides immutable, slot-optimized dataclasses and Pydantic validation models
supporting safe parsing, serialization, and historical metrics tracking.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from core.common.constants import COUNTRY_ALIASES
from pydantic import BaseModel, Field

# =====================================================================
# Shared Parsing Helpers & Mixins (DRY Principles)
# =====================================================================


class DictAccessMixin:
    """Mixin providing dictionary-like item access (__getitem__) to dataclasses."""

    __slots__ = ()

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


def _get_float(data: dict[str, Any], key: str, default: float | None = None) -> float | None:
    val: Any = data.get(key)
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _get_int(data: dict[str, Any], key: str, default: int | None = None) -> int | None:
    val: Any = data.get(key)
    if val is None or val == "":
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _get_str(data: dict[str, Any], key: str, default: str | None = None) -> str | None:
    val: Any = data.get(key)
    if val is None or val == "":
        return default
    return str(val).strip() or default


# =====================================================================
# Domain Models
# =====================================================================


@dataclass(frozen=True, slots=True)
class Quotation(DictAccessMixin):
    """Represents a market quotation and pricing details for a specific ticker at a point in time.

    Attributes:
        price: The converted or normalized price value (typically in EUR).
        currency: The target currency code (e.g., 'EUR').
        timestamp: Exact datetime (UTC) when the quotation was fetched or recorded.
        native_price: The original asset price in its native trading currency.
        native_currency: The original trading currency code (e.g., 'USD', 'DKK').
    """

    price: float
    currency: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    native_price: float | None = None
    native_currency: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "price": self.price,
            "currency": self.currency,
            "timestamp": self.timestamp.isoformat(),
            "native_price": self.native_price,
            "native_currency": self.native_currency,
        }


@dataclass(frozen=True, slots=True)
class Asset(DictAccessMixin):
    """Represents an individual asset configuration within the user's portfolio.

    Attributes:
        name: Descriptive display name of the asset.
        isin: International Securities Identification Number.
        yahoo_ticker: Symbol format used by yfinance for fetching market data.
        quantity: Total number of units currently held.
        average_buy_price: Weighted average purchase price per unit.
        asset_type: Classification category (e.g., 'STOCK', 'ETF').
        xtb_name: Exact instrument display name matching the XTB broker platform.
        xtb_ticker: Specific trading symbol format used on the XTB broker.
        just_etf_ticker: Specific ticker or identifier used on the justETF platform.
        native_currency: The original currency in which the asset is traded (e.g., 'EUR', 'USD', 'DKK').
    """

    name: str
    isin: str
    yahoo_ticker: str
    quantity: float
    average_buy_price: float
    asset_type: str = "STOCK"
    xtb_name: str | None = None
    xtb_ticker: str | None = None
    just_etf_ticker: str | None = None
    native_currency: str = "EUR"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Asset:
        raw_type: str = str(data.get("asset_type") or data.get("type") or "STOCK").upper()
        resolved_yahoo = str(data.get("yahoo_ticker") or data.get("symbol", ""))
        resolved_just_etf = _get_str(data, "just_etf_ticker") or _get_str(data, "just_etf")
        resolved_currency = str(
            data.get("native_currency") or data.get("currency") or "EUR"
        ).upper()

        return cls(
            name=str(data.get("name", "")),
            isin=str(data.get("isin", "")),
            yahoo_ticker=resolved_yahoo,
            quantity=float(data.get("quantity", 0.0)),
            average_buy_price=float(
                data.get("averageBuyPrice", data.get("average_buy_price", 0.0))
            ),
            asset_type=raw_type,
            xtb_name=_get_str(data, "xtb_name"),
            xtb_ticker=_get_str(data, "xtb_ticker"),
            just_etf_ticker=resolved_just_etf,
            native_currency=resolved_currency,
        )

    @property
    def acquisition_cost(self) -> float:
        return self.quantity * self.average_buy_price

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AssetSnapshot(DictAccessMixin):
    """Represents the historical valuation and metrics of an asset holding at a specific point in time.

    Attributes:
        ticker: Canonical generic ticker identifier.
        isin: International Securities Identification Number.
        asset_type: Classification category (e.g., 'STOCK', 'ETF').
        native_currency: The trading currency code (e.g., 'EUR', 'USD', 'DKK').
        yahoo_ticker: Symbol format used by yfinance for fetching market data.
        just_etf_ticker: Specific ticker or identifier used on the justETF platform.
        quantity: Total number of units held.
        average_buy_price: Purchase price per unit in native currency.
        market_price: Current market price per unit in native currency.
        total_cost_eur: Total acquisition cost in Euros.
        market_value_eur: Total market valuation of the position in Euros.
        unrealized_pnl_eur: Unrealized profit or loss in Euros.
        unrealized_pnl_pct: Unrealized profit or loss percentage.
        target_allocation_pct: Target portfolio allocation percentage.
        current_allocation_pct: Current portfolio allocation percentage.
    """

    ticker: str
    isin: str
    asset_type: str
    native_currency: str
    yahoo_ticker: str
    just_etf_ticker: str | None
    quantity: float
    average_buy_price: float
    market_price: float
    total_cost_eur: float
    market_value_eur: float
    unrealized_pnl_eur: float
    unrealized_pnl_pct: float
    target_allocation_pct: float
    current_allocation_pct: float

    @property
    def allocation_drift(self) -> float:
        return self.current_allocation_pct - self.target_allocation_pct

    @property
    def is_profitable(self) -> bool:
        return self.unrealized_pnl_eur > 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssetSnapshot:
        if "native_currency" not in data or not data["native_currency"]:
            raise ValueError(
                f"[models] Asset snapshot for '{data.get('ticker', 'UNKNOWN')}' "
                "violates contract: mandatory property 'native_currency' is missing."
            )
        native_currency: str = str(data["native_currency"]).upper()
        currency_suffix: str = native_currency.lower()

        avg_price_key: str = f"average_buy_price_{currency_suffix}"
        market_price_key: str = f"market_price_{currency_suffix}"

        if avg_price_key not in data:
            raise KeyError(f"[models] Asset snapshot missing mandatory key '{avg_price_key}'.")
        if market_price_key not in data:
            raise KeyError(f"[models] Asset snapshot missing mandatory key '{market_price_key}'.")

        return cls(
            ticker=str(data.get("ticker", "")),
            isin=str(data.get("isin", "")),
            asset_type=str(data.get("asset_type", "STOCK")).upper(),
            native_currency=native_currency,
            yahoo_ticker=str(data.get("yahoo_ticker") or data.get("ticker", "")),
            just_etf_ticker=_get_str(data, "just_etf_ticker") or _get_str(data, "just_etf"),
            quantity=_get_float(data, "quantity", 0.0) or 0.0,
            average_buy_price=_get_float(data, avg_price_key, 0.0) or 0.0,
            market_price=_get_float(data, market_price_key, 0.0) or 0.0,
            total_cost_eur=_get_float(data, "total_cost_eur", 0.0) or 0.0,
            market_value_eur=_get_float(data, "market_value_eur", 0.0) or 0.0,
            unrealized_pnl_eur=_get_float(data, "unrealized_pnl_eur", 0.0) or 0.0,
            unrealized_pnl_pct=_get_float(data, "unrealized_pnl_pct", 0.0) or 0.0,
            target_allocation_pct=_get_float(data, "target_allocation_pct", 0.0) or 0.0,
            current_allocation_pct=_get_float(data, "current_allocation_pct", 0.0) or 0.0,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot(DictAccessMixin):
    """Represents a complete portfolio valuation snapshot at a specific point in time.

    Attributes:
        date: Calendar date of the snapshot (e.g., '2026-11-11').
        timestamp: Exact ISO timestamp when the snapshot was recorded.
        total_invested_eur: Total capital invested in Euros.
        total_market_value_eur: Total market valuation of the portfolio in Euros.
        unrealized_pnl_eur: Total unrealized profit or loss in Euros.
        unrealized_pnl_pct: Total unrealized profit or loss percentage.
        currencies_rate: Dictionary of currency conversion rates (e.g., EURUSD).
        breakdown: Valuation breakdown across asset classes (e.g., stocks, etfs).
        holdings: List of individual asset snapshots.
    """

    date: str
    timestamp: str
    total_invested_eur: float
    total_market_value_eur: float
    unrealized_pnl_eur: float
    unrealized_pnl_pct: float
    currencies_rate: dict[str, float | None] = field(default_factory=dict)
    breakdown: dict[str, float] = field(default_factory=dict)
    holdings: list[AssetSnapshot] = field(default_factory=list)

    @property
    def total_value_eur(self) -> float:
        return self.total_market_value_eur

    @property
    def assets_snapshot(self) -> list[AssetSnapshot]:
        return self.holdings

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PortfolioSnapshot:
        if "date" not in data or not data["date"]:
            raise ValueError(
                "[models] Portfolio snapshot violates contract: mandatory property 'date' is missing."
            )

        if not any(k in data for k in ("holdings", "assets_snapshot", "asset")):
            raise KeyError("[models] Portfolio snapshot violates contract: missing holdings key.")

        raw_market_val = (
            _get_float(data, "total_market_value_eur") or _get_float(data, "total_value_eur") or 0.0
        )
        raw_holdings = (
            data.get("holdings") or data.get("assets_snapshot") or data.get("asset") or []
        )
        if not isinstance(raw_holdings, list):
            raw_holdings = []

        parsed_holdings = [
            AssetSnapshot.from_dict(item) for item in raw_holdings if isinstance(item, dict)
        ]

        return cls(
            date=str(data["date"]),
            timestamp=str(data.get("timestamp", "")),
            total_invested_eur=_get_float(data, "total_invested_eur", 0.0) or 0.0,
            total_market_value_eur=float(raw_market_val),
            unrealized_pnl_eur=_get_float(data, "unrealized_pnl_eur", 0.0) or 0.0,
            unrealized_pnl_pct=_get_float(data, "unrealized_pnl_pct", 0.0) or 0.0,
            currencies_rate=dict(data.get("currencies_rate", {})),
            breakdown=dict(data.get("breakdown", {})),
            holdings=parsed_holdings,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Holding(DictAccessMixin):
    """Represents an individual stock or asset holding within an ETF.

    Attributes:
        name: Descriptive display name of the underlying holding asset.
        isin: International Securities Identification Number of the holding.
        weight_pct: Percentage weight of the holding within the ETF portfolio.
        just_etf_ticker: Specific ticker or identifier used on the justETF platform.
    """

    name: str
    isin: str
    weight_pct: float
    just_etf_ticker: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Holding:
        if not data.get("isin"):
            raise ValueError("[models] Holding missing mandatory property 'isin'.")
        if not data.get("name"):
            raise ValueError("[models] Holding missing mandatory property 'name'.")
        if "weight_pct" not in data:
            raise KeyError("[models] Holding missing mandatory key 'weight_pct'.")

        return cls(
            name=str(data["name"]),
            isin=str(data["isin"]),
            weight_pct=_get_float(data, "weight_pct", 0.0) or 0.0,
            just_etf_ticker=_get_str(data, "just_etf_ticker") or _get_str(data, "just_etf"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SectorExposure(DictAccessMixin):
    """Represents sector breakdown weight within an ETF.

    Attributes:
        sector_name: Descriptive name of the market sector.
        weight_pct: Percentage weight of the sector within the ETF.
    """

    sector_name: str
    weight_pct: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SectorExposure:
        if not data.get("sector_name"):
            raise ValueError("[models] Sector exposure missing mandatory property 'sector_name'.")
        if "weight_pct" not in data:
            raise KeyError("[models] Sector exposure missing mandatory key 'weight_pct'.")

        return cls(
            sector_name=str(data["sector_name"]),
            weight_pct=_get_float(data, "weight_pct", 0.0) or 0.0,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CountryExposure(DictAccessMixin):
    """Represents country breakdown weight within an ETF.

    Attributes:
        country_name: Descriptive name of the country.
        weight_pct: Percentage weight of the country within the ETF.
    """

    country_name: str
    weight_pct: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CountryExposure:
        if not data.get("country_name"):
            raise ValueError("[models] Country exposure missing mandatory property 'country_name'.")
        if "weight_pct" not in data:
            raise KeyError("[models] Country exposure missing mandatory key 'weight_pct'.")

        raw_name: str = str(data["country_name"]).strip()
        normalized_name: str = COUNTRY_ALIASES.get(raw_name.upper(), raw_name)

        return cls(
            country_name=normalized_name,
            weight_pct=_get_float(data, "weight_pct", 0.0) or 0.0,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ETFMarketData(DictAccessMixin):
    """Market data for an ETF fetched from market and fund sources.

    Attributes:
        price: Current market price of the ETF.
        native_currency: Trading currency code of the ETF (e.g., 'EUR', 'USD').
        just_etf_ticker: Specific ticker or identifier used on the justETF platform.
        nav_price: Net Asset Value (NAV) price if available.
        fifty_two_week_high: Highest price recorded over the past 52 weeks.
        fifty_two_week_low: Lowest price recorded over the past 52 weeks.
        fifty_two_week_change_pct: Percentage price change over the past 52 weeks.
        fifty_day_average: 50-day moving average price.
        two_hundred_day_average: 200-day moving average price.
        average_volume: Average daily trading volume.
    """

    price: float | None = None
    native_currency: str | None = None
    just_etf_ticker: str | None = None
    nav_price: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    fifty_two_week_change_pct: float | None = None
    fifty_day_average: float | None = None
    two_hundred_day_average: float | None = None
    average_volume: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ETFMarketData:
        return cls(
            price=_get_float(data, "price"),
            native_currency=_get_str(data, "currency"),
            just_etf_ticker=_get_str(data, "just_etf_ticker") or _get_str(data, "just_etf"),
            nav_price=_get_float(data, "nav_price"),
            fifty_two_week_high=_get_float(data, "fifty_two_week_high"),
            fifty_two_week_low=_get_float(data, "fifty_two_week_low"),
            fifty_two_week_change_pct=_get_float(data, "fifty_two_week_change_pct"),
            fifty_day_average=_get_float(data, "fifty_day_average"),
            two_hundred_day_average=_get_float(data, "two_hundred_day_average"),
            average_volume=_get_int(data, "average_volume"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ETFDetails(DictAccessMixin):
    """Consolidates ETF holdings, sector exposure, country exposure,
    and fund metadata.

    Attributes:
        holdings: List of underlying asset holdings within the ETF.
        sector_breakdown: Breakdown weights across market sectors.
        country_breakdown: Breakdown weights across geographical regions/countries.
        ter_pct: Total Expense Ratio (TER) percentage.
        inception_date: Fund inception or launch date.
        fund_size_eur_m: Total fund size in millions of Euros.
        holdings_count: Total number of securities held by the fund.
        replication: Replication method (e.g., 'Physical', 'Synthetic').
        distribution_policy: Distribution policy (e.g., 'Accumulating', 'Distributing').
        index_name: Underlying tracked index name.
        fund_currency: Base currency of the fund.
        volatility_1y_pct: One-year historical volatility percentage.
    """

    holdings: list[Holding]
    sector_breakdown: list[SectorExposure]
    country_breakdown: list[CountryExposure]
    ter_pct: float | None = None
    inception_date: str | None = None
    fund_size_eur_m: float | None = None
    holdings_count: int | None = None
    replication: str | None = None
    distribution_policy: str | None = None
    index_name: str | None = None
    fund_currency: str | None = None
    volatility_1y_pct: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ETFDetails:
        return cls(
            holdings=[
                Holding.from_dict(item)
                for item in data.get("holdings", [])
                if isinstance(item, dict)
            ],
            sector_breakdown=[
                SectorExposure.from_dict(item)
                for item in data.get("sector_breakdown", [])
                if isinstance(item, dict)
            ],
            country_breakdown=[
                CountryExposure.from_dict(item)
                for item in data.get("country_breakdown", [])
                if isinstance(item, dict)
            ],
            ter_pct=_get_float(data, "ter_pct"),
            inception_date=_get_str(data, "inception_date"),
            fund_size_eur_m=_get_float(data, "fund_size_eur_m"),
            holdings_count=_get_int(data, "holdings_count"),
            replication=_get_str(data, "replication"),
            distribution_policy=_get_str(data, "distribution_policy"),
            index_name=_get_str(data, "index_name"),
            fund_currency=_get_str(data, "fund_currency"),
            volatility_1y_pct=_get_float(data, "volatility_1y_pct"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StockDetails(DictAccessMixin):
    """Consolidates stock fundamental metrics, valuation ratios, and market data.

    Attributes:
        market_cap: Total market capitalization of the company.
        pe_ratio: Price-to-Earnings (P/E) ratio based on trailing earnings.
        forward_pe: Forward Price-to-Earnings (P/E) ratio based on projected earnings.
        dividend_yield_pct: Annual dividend yield percentage.
        fifty_two_week_high: Highest price recorded over the past 52 weeks.
        fifty_two_week_low: Lowest price recorded over the past 52 weeks.
        fifty_two_week_change_pct: Percentage price change over the past 52 weeks.
        fifty_day_average: 50-day moving average price.
        two_hundred_day_average: 200-day moving average price.
        average_volume: Average daily trading volume.
        sector: Market sector classification.
        industry: Specific industry classification.
        country: Country of domicile or primary operation.
        price_to_book: Price-to-Book (P/B) ratio.
        peg_ratio: Price/Earnings-to-Growth (PEG) ratio.
        beta: Measure of stock volatility relative to the market.
        profit_margins_pct: Net profit margin percentage.
        gross_margins_pct: Gross profit margin percentage.
        operating_margins_pct: Operating margin percentage.
        revenue_growth_pct: Quarterly or annual revenue growth percentage.
        earnings_growth_pct: Quarterly or annual earnings growth percentage.
        return_on_equity_pct: Return on Equity (ROE) percentage.
        return_on_assets_pct: Return on Assets (ROA) percentage.
        total_debt_to_equity: Total debt-to-equity financial leverage ratio.
        free_cashflow: Free cash flow available to the company.
        short_ratio: Short interest ratio (days to cover).
        target_mean_price: Analyst consensus mean target price.
        target_high_price: Analyst consensus highest target price.
        target_low_price: Analyst consensus lowest target price.
        number_of_analyst_opinions: Total count of covering analysts providing opinions.
        recommendation_key: Consensus recommendation key (e.g., 'buy', 'hold').
        eps_trailing_ttm: Trailing twelve months Earnings Per Share (EPS).
        eps_forward: Projected forward Earnings Per Share (EPS).
        currency: Base trading currency of the stock fundamental values.
    """

    market_cap: float | None = None
    pe_ratio: float | None = None
    forward_pe: float | None = None
    dividend_yield_pct: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    fifty_two_week_change_pct: float | None = None
    fifty_day_average: float | None = None
    two_hundred_day_average: float | None = None
    average_volume: int | None = None
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    price_to_book: float | None = None
    peg_ratio: float | None = None
    beta: float | None = None
    profit_margins_pct: float | None = None
    gross_margins_pct: float | None = None
    operating_margins_pct: float | None = None
    revenue_growth_pct: float | None = None
    earnings_growth_pct: float | None = None
    return_on_equity_pct: float | None = None
    return_on_assets_pct: float | None = None
    total_debt_to_equity: float | None = None
    free_cashflow: float | None = None
    short_ratio: float | None = None
    target_mean_price: float | None = None
    target_high_price: float | None = None
    target_low_price: float | None = None
    number_of_analyst_opinions: int | None = None
    recommendation_key: str | None = None
    eps_trailing_ttm: float | None = None
    eps_forward: float | None = None
    currency: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StockDetails:
        return cls(
            market_cap=_get_float(data, "market_cap"),
            pe_ratio=_get_float(data, "pe_ratio"),
            forward_pe=_get_float(data, "forward_pe"),
            dividend_yield_pct=_get_float(data, "dividend_yield_pct"),
            fifty_two_week_high=_get_float(data, "fifty_two_week_high"),
            fifty_two_week_low=_get_float(data, "fifty_two_week_low"),
            fifty_two_week_change_pct=_get_float(data, "fifty_two_week_change_pct"),
            fifty_day_average=_get_float(data, "fifty_day_average"),
            two_hundred_day_average=_get_float(data, "two_hundred_day_average"),
            average_volume=_get_int(data, "average_volume"),
            sector=_get_str(data, "sector"),
            industry=_get_str(data, "industry"),
            country=_get_str(data, "country"),
            price_to_book=_get_float(data, "price_to_book"),
            peg_ratio=_get_float(data, "peg_ratio"),
            beta=_get_float(data, "beta"),
            profit_margins_pct=_get_float(data, "profit_margins_pct"),
            gross_margins_pct=_get_float(data, "gross_margins_pct"),
            operating_margins_pct=_get_float(data, "operating_margins_pct"),
            revenue_growth_pct=_get_float(data, "revenue_growth_pct"),
            earnings_growth_pct=_get_float(data, "earnings_growth_pct"),
            return_on_equity_pct=_get_float(data, "return_on_equity_pct"),
            return_on_assets_pct=_get_float(data, "return_on_assets_pct"),
            total_debt_to_equity=_get_float(data, "total_debt_to_equity"),
            free_cashflow=_get_float(data, "free_cashflow"),
            short_ratio=_get_float(data, "short_ratio"),
            target_mean_price=_get_float(data, "target_mean_price"),
            target_high_price=_get_float(data, "target_high_price"),
            target_low_price=_get_float(data, "target_low_price"),
            number_of_analyst_opinions=_get_int(data, "number_of_analyst_opinions"),
            recommendation_key=_get_str(data, "recommendation_key"),
            eps_trailing_ttm=_get_float(data, "eps_trailing_ttm"),
            eps_forward=_get_float(data, "eps_forward"),
            currency=_get_str(data, "currency"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RecommendationAction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class UrgencyLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RebalanceRecommendation(BaseModel):
    action: RecommendationAction
    confidence_score: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(max_length=250)
    target_allocation_pct: float = Field(ge=0.0, le=100.0)
    urgency_level: UrgencyLevel
    risk_score: int = Field(ge=1, le=5)
    valuation_score: int = Field(ge=1, le=10)
    expected_dividend_yield_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    ter_impact_assessment: str | None = Field(default=None, max_length=100)


@dataclass(frozen=True, slots=True)
class TimeSeriesPoint(DictAccessMixin):
    date: str
    value: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TimeSeriesPoint:
        return cls(
            date=_get_str(data, "date") or "",
            value=_get_float(data, "value", 0.0) or 0.0,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AssetTimeSeries(DictAccessMixin):
    isin: str
    name: str
    asset_type: str
    value_history: list[TimeSeriesPoint] = field(default_factory=list)
    quantity_history: list[TimeSeriesPoint] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssetTimeSeries:
        raw_values: list[Any] = data.get("value_history", [])
        raw_quantities: list[Any] = data.get("quantity_history", [])

        parsed_values = [
            TimeSeriesPoint.from_dict(item) if isinstance(item, dict) else item
            for item in raw_values
            if isinstance(item, (dict, TimeSeriesPoint))
        ]
        parsed_quantities = [
            TimeSeriesPoint.from_dict(item) if isinstance(item, dict) else item
            for item in raw_quantities
            if isinstance(item, (dict, TimeSeriesPoint))
        ]

        return cls(
            isin=str(data.get("isin", "")).strip(),
            name=str(data.get("name", "")).strip(),
            asset_type=str(data.get("asset_type", "STOCK")).upper(),
            value_history=parsed_values,
            quantity_history=parsed_quantities,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AssetClassTimeSeries(DictAccessMixin):
    asset_type: str
    value_history: list[TimeSeriesPoint] = field(default_factory=list)
    share_history: list[TimeSeriesPoint] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssetClassTimeSeries:
        raw_values: list[Any] = data.get("value_history", [])
        raw_shares: list[Any] = data.get("share_history", [])

        parsed_values = [
            TimeSeriesPoint.from_dict(item) if isinstance(item, dict) else item
            for item in raw_values
            if isinstance(item, (dict, TimeSeriesPoint))
        ]
        parsed_shares = [
            TimeSeriesPoint.from_dict(item) if isinstance(item, dict) else item
            for item in raw_shares
            if isinstance(item, (dict, TimeSeriesPoint))
        ]

        return cls(
            asset_type=str(data.get("asset_type", "STOCK")).upper(),
            value_history=parsed_values,
            share_history=parsed_shares,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PortfolioTimeSeries(DictAccessMixin):
    value_history: list[TimeSeriesPoint] = field(default_factory=list)
    ath_history: list[TimeSeriesPoint] = field(default_factory=list)
    drawdown_history: list[TimeSeriesPoint] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PortfolioTimeSeries:
        raw_values: list[Any] = data.get("value_history", [])
        raw_ath: list[Any] = data.get("ath_history", [])
        raw_drawdowns: list[Any] = data.get("drawdown_history", [])

        return cls(
            value_history=[TimeSeriesPoint.from_dict(i) for i in raw_values if isinstance(i, dict)],
            ath_history=[TimeSeriesPoint.from_dict(i) for i in raw_ath if isinstance(i, dict)],
            drawdown_history=[
                TimeSeriesPoint.from_dict(i) for i in raw_drawdowns if isinstance(i, dict)
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AssetPerformanceSummary(DictAccessMixin):
    isin: str
    name: str
    asset_type: str
    latest_quantity: float
    latest_value_eur: float
    cost_basis_eur: float
    roi_eur: float
    roi_percent: float
    portfolio_share_percent: float
    market_price: float | None = None
    average_buy_price: float | None = None

    @property
    def is_profitable(self) -> bool:
        return self.roi_eur > 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssetPerformanceSummary:
        return cls(
            isin=str(data.get("isin", "")).strip(),
            name=str(data.get("name", "")).strip(),
            asset_type=str(data.get("asset_type", "STOCK")).upper(),
            latest_quantity=_get_float(data, "latest_quantity", 0.0) or 0.0,
            latest_value_eur=_get_float(data, "latest_value_eur", 0.0) or 0.0,
            cost_basis_eur=_get_float(data, "cost_basis_eur", 0.0) or 0.0,
            roi_eur=_get_float(data, "roi_eur", 0.0) or 0.0,
            roi_percent=_get_float(data, "roi_percent", 0.0) or 0.0,
            portfolio_share_percent=_get_float(data, "portfolio_share_percent", 0.0) or 0.0,
            market_price=_get_float(data, "market_price"),
            average_buy_price=_get_float(data, "average_buy_price"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DashboardOverview(DictAccessMixin):
    portfolio_history: PortfolioTimeSeries
    asset_series: list[AssetTimeSeries] = field(default_factory=list)
    class_series: list[AssetClassTimeSeries] = field(default_factory=list)
    asset_summaries: list[AssetPerformanceSummary] = field(default_factory=list)
    top_growth_contributor: str | None = None
    max_drawdown_percent: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DashboardOverview:
        raw_portfolio = data.get("portfolio_history", {})
        portfolio_history = (
            PortfolioTimeSeries.from_dict(raw_portfolio)
            if isinstance(raw_portfolio, dict)
            else PortfolioTimeSeries()
        )

        return cls(
            portfolio_history=portfolio_history,
            asset_series=[
                AssetTimeSeries.from_dict(i)
                for i in data.get("asset_series", [])
                if isinstance(i, dict)
            ],
            class_series=[
                AssetClassTimeSeries.from_dict(i)
                for i in data.get("class_series", [])
                if isinstance(i, dict)
            ],
            asset_summaries=[
                AssetPerformanceSummary.from_dict(i)
                for i in data.get("asset_summaries", [])
                if isinstance(i, dict)
            ],
            top_growth_contributor=_get_str(data, "top_growth_contributor"),
            max_drawdown_percent=_get_float(data, "max_drawdown_percent", 0.0) or 0.0,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio_history": self.portfolio_history.to_dict(),
            "asset_series": [item.to_dict() for item in self.asset_series],
            "class_series": [item.to_dict() for item in self.class_series],
            "asset_summaries": [item.to_dict() for item in self.asset_summaries],
            "top_growth_contributor": self.top_growth_contributor,
            "max_drawdown_percent": self.max_drawdown_percent,
        }


@dataclass(frozen=True, slots=True)
class GrowthMilestone(DictAccessMixin):
    year: int
    total_invested: float
    compound_interest: float
    projected_value: float
    inflation_adjusted_value: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GrowthMilestone:
        return cls(
            year=_get_int(data, "year", 0) or 0,
            total_invested=_get_float(data, "total_invested", 0.0) or 0.0,
            compound_interest=_get_float(data, "compound_interest", 0.0) or 0.0,
            projected_value=_get_float(data, "projected_value", 0.0) or 0.0,
            inflation_adjusted_value=_get_float(data, "inflation_adjusted_value", 0.0) or 0.0,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GrowthProjectionScenario(DictAccessMixin):
    name: str
    annual_return_pct: float
    monthly_contribution: float
    progression: list[GrowthMilestone] = field(default_factory=list)
    milestones: dict[int, GrowthMilestone] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GrowthProjectionScenario:
        raw_progression = data.get("progression", [])
        progression = [
            GrowthMilestone.from_dict(item) for item in raw_progression if isinstance(item, dict)
        ]

        raw_milestones = data.get("milestones", {})
        milestones: dict[int, GrowthMilestone] = {}
        if isinstance(raw_milestones, dict):
            for yr_key, ms_val in raw_milestones.items():
                try:
                    int_yr = int(yr_key)
                    if isinstance(ms_val, dict):
                        milestones[int_yr] = GrowthMilestone.from_dict(ms_val)
                except (ValueError, TypeError):
                    continue

        return cls(
            name=_get_str(data, "name") or "",
            annual_return_pct=_get_float(data, "annual_return_pct", 0.0) or 0.0,
            monthly_contribution=_get_float(data, "monthly_contribution", 0.0) or 0.0,
            progression=progression,
            milestones=milestones,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "annual_return_pct": self.annual_return_pct,
            "monthly_contribution": self.monthly_contribution,
            "progression": [item.to_dict() for item in self.progression],
            "milestones": {str(yr): ms.to_dict() for yr, ms in self.milestones.items()},
        }


@dataclass(frozen=True, slots=True)
class GrowthProjectionResult(DictAccessMixin):
    """Consolidated result container for portfolio compound growth projections.

    Attributes:
        initial_value: Starting portfolio valuation in Euros at the beginning of the projection.
        monthly_contribution: Baseline regular monthly contribution amount in Euros.
        scenarios: List of simulated GrowthProjectionScenario options.
        historical_cagr_pct: Historical Compound Annual Growth Rate (CAGR) percentage, if available.
        primary_scenario: The default or recommended primary GrowthProjectionScenario, if selected.
    """

    initial_value: float
    monthly_contribution: float
    scenarios: list[GrowthProjectionScenario] = field(default_factory=list)
    historical_cagr_pct: float | None = None
    primary_scenario: GrowthProjectionScenario | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GrowthProjectionResult:
        raw_scenarios = data.get("scenarios", [])
        scenarios = [
            GrowthProjectionScenario.from_dict(item)
            for item in raw_scenarios
            if isinstance(item, dict)
        ]

        raw_primary = data.get("primary_scenario")
        primary_scenario = (
            GrowthProjectionScenario.from_dict(raw_primary)
            if isinstance(raw_primary, dict)
            else None
        )

        return cls(
            initial_value=_get_float(data, "initial_value", 0.0) or 0.0,
            monthly_contribution=_get_float(data, "monthly_contribution", 0.0) or 0.0,
            scenarios=scenarios,
            historical_cagr_pct=_get_float(data, "historical_cagr_pct"),
            primary_scenario=primary_scenario,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_value": self.initial_value,
            "monthly_contribution": self.monthly_contribution,
            "scenarios": [sc.to_dict() for sc in self.scenarios],
            "historical_cagr_pct": self.historical_cagr_pct,
            "primary_scenario": self.primary_scenario.to_dict() if self.primary_scenario else None,
        }
