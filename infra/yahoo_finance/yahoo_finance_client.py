"""Infrastructure client for fetching market data and asset details using yfinance."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import yfinance as yf

from core.models import ETFMarketData, Quotation, StockDetails


class YahooFinanceError(Exception):
    """Raised when fetching data from Yahoo Finance fails."""

    pass


class YahooFinanceClient:
    """Client for retrieving market quotations, stock fundamentals, and ETF market data via yfinance."""

    def __init__(self) -> None:
        pass

    def _fetch_ticker_market_data(self, ticker: str) -> tuple[float, str, dict[str, Any]]:
        """Helper to fetch info, history, price, and currency for a ticker efficiently."""
        try:
            t: yf.Ticker = yf.Ticker(ticker)
            try:
                info = t.info
            except Exception as e:
                raise YahooFinanceError(
                    f"Failed to retrieve info for ticker '{ticker}': {e}"
                ) from e

            history: Any = t.history(period="1d")
            if history.empty:
                raise YahooFinanceError(f"No price history returned for ticker '{ticker}'.")

            latest_row: Any = history.iloc[-1]
            price: float | None = _safe_float(latest_row.get("Close"))
            if price is None:
                raise YahooFinanceError(f"Invalid or missing close price for ticker '{ticker}'.")

            currency_str = info.get("currency")
            if not currency_str:
                raise YahooFinanceError(f"Currency information is missing for ticker '{ticker}'.")
            currency: str = str(currency_str).upper()

            return price, currency, info
        except YahooFinanceError:
            raise
        except Exception as e:
            raise YahooFinanceError(f"Failed to fetch market data for ticker '{ticker}': {e}") from e

    def get_quotation(self, ticker: str) -> Quotation:
        """Fetches the latest quotation for a given ticker symbol."""
        try:
            price, currency, _ = self._fetch_ticker_market_data(ticker)
            return Quotation(
                price=price,
                currency=currency,
                timestamp=datetime.now(UTC),
                native_price=price,
                native_currency=currency,
            )
        except YahooFinanceError:
            raise
        except Exception as e:
            raise YahooFinanceError(f"Failed to fetch quotation for ticker '{ticker}': {e}") from e

    def get_stock_details(self, ticker: str) -> StockDetails:
        """Fetches fundamental metrics and valuation ratios for a stock ticker."""
        try:
            t: yf.Ticker = yf.Ticker(ticker)
            try:
                info = t.info
            except Exception as e:
                raise YahooFinanceError(
                    f"Failed to retrieve info for ticker '{ticker}': {e}"
                ) from e

            return StockDetails(
                market_cap=_safe_float(info.get("marketCap")),
                pe_ratio=_safe_float(info.get("trailingPE")),
                forward_pe=_safe_float(info.get("forwardPE")),
                dividend_yield_pct=_safe_float(info.get("dividendYield"), scale=100.0),
                fifty_two_week_high=_safe_float(info.get("fiftyTwoWeekHigh")),
                fifty_two_week_low=_safe_float(info.get("fiftyTwoWeekLow")),
                fifty_two_week_change_pct=_safe_float(info.get("52WeekChange"), scale=100.0),
                fifty_day_average=_safe_float(info.get("fiftyDayAverage")),
                two_hundred_day_average=_safe_float(info.get("twoHundredDayAverage")),
                average_volume=_safe_int(info.get("averageVolume")),
                sector=_safe_str(info.get("sector")),
                industry=_safe_str(info.get("industry")),
                country=_safe_str(info.get("country")),
                price_to_book=_safe_float(info.get("priceToBook")),
                peg_ratio=_safe_float(info.get("pegRatio")),
                beta=_safe_float(info.get("beta")),
                profit_margins_pct=_safe_float(info.get("profitMargins"), scale=100.0),
                gross_margins_pct=_safe_float(info.get("grossMargins"), scale=100.0),
                operating_margins_pct=_safe_float(info.get("operatingMargins"), scale=100.0),
                revenue_growth_pct=_safe_float(info.get("revenueGrowth"), scale=100.0),
                earnings_growth_pct=_safe_float(info.get("earningsGrowth"), scale=100.0),
                return_on_equity_pct=_safe_float(info.get("returnOnEquity"), scale=100.0),
                return_on_assets_pct=_safe_float(info.get("returnOnAssets"), scale=100.0),
                total_debt_to_equity=_safe_float(info.get("debtToEquity")),
                free_cashflow=_safe_float(info.get("freeCashflow")),
                short_ratio=_safe_float(info.get("shortRatio")),
                target_mean_price=_safe_float(info.get("targetMeanPrice")),
                target_high_price=_safe_float(info.get("targetHighPrice")),
                target_low_price=_safe_float(info.get("targetLowPrice")),
                number_of_analyst_opinions=_safe_int(info.get("numberOfAnalystOpinions")),
                recommendation_key=_safe_str(info.get("recommendationKey")),
                eps_trailing_ttm=_safe_float(info.get("trailingEps")),
                eps_forward=_safe_float(info.get("forwardEps")),
                currency=_safe_str(info.get("currency")),
            )
        except YahooFinanceError:
            raise
        except Exception as e:
            raise YahooFinanceError(
                f"Failed to fetch stock details for ticker '{ticker}': {e}"
            ) from e

    def get_etf_market_data(self, ticker: str) -> ETFMarketData:
        """Fetches market pricing and moving averages for an ETF ticker efficiently."""
        try:
            price, currency, info = self._fetch_ticker_market_data(ticker)

            return ETFMarketData(
                price=price,
                native_currency=currency,
                just_etf_ticker=None,
                nav_price=_safe_float(info.get("navPrice")),
                fifty_two_week_high=_safe_float(info.get("fiftyTwoWeekHigh")),
                fifty_two_week_low=_safe_float(info.get("fiftyTwoWeekLow")),
                fifty_two_week_change_pct=_safe_float(info.get("52WeekChange"), scale=100.0),
                fifty_day_average=_safe_float(info.get("fiftyDayAverage")),
                two_hundred_day_average=_safe_float(info.get("twoHundredDayAverage")),
                average_volume=_safe_int(info.get("averageVolume")),
            )
        except YahooFinanceError:
            raise
        except Exception as e:
            raise YahooFinanceError(
                f"Failed to fetch ETF market data for ticker '{ticker}': {e}"
            ) from e


def _safe_float(val: Any, scale: float = 1.0) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val) * scale
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> int | None:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_str(val: Any) -> str | None:
    if val is None or val == "":
        return None
    return str(val).strip() or None