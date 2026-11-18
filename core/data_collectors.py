"""Data provider abstractions and implementations for stocks and ETFs,
combining real-time market data from yfinance and fundamental metadata.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import yfinance as yf
from core_lib.logger import logger

from config import get_settings
from core.currency_exchange import get_exchange_rate
from core.models import Asset, ETFDetails, ETFMarketData, Quotation, StockDetails
from core.repositories import (
    ETFCacheRepository,
    JsonETFCacheRepository,
    SqliteOpportunityRepository,
)
from infra.database.connection import DEFAULT_DB_PATH, get_db_context
from infra.database.schema import initialize_database


class AssetDataProvider(Protocol):
    """Protocol defining core operations for fetching asset pricing and metadata."""

    def get_price(self, asset: Asset) -> Quotation | None:
        """Retrieves current market quotation for an asset."""
        ...

    def get_details(
        self, asset: Asset, force_refresh: bool = False
    ) -> ETFDetails | StockDetails | None:
        """Retrieves detailed fundamentals or composition for an asset."""
        ...


class StockProvider:
    """Data provider for standard equity and stock assets using yfinance."""

    def get_price(self, asset: Asset) -> Quotation | None:
        """Fetches the latest market quotation for a stock asset, converting to EUR if necessary.

        Args:
            asset: Asset instance representing the stock.

        Returns:
            A Quotation object containing normalized pricing details, or None on failure.
        """
        if not asset.yahoo_ticker:
            logger.error(
                f"[data collectors] No Yahoo ticker provided for stock asset '{asset.name}'."
            )
            return None

        try:
            ticker: yf.Ticker = yf.Ticker(asset.yahoo_ticker)
            info: dict[str, Any] = ticker.info

            price: float | None = (
                info.get("regularMarketPrice")
                or info.get("currentPrice")
                or info.get("previousClose")
            )

            if not price:
                hist: Any = ticker.history(period="1d")
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])

            if price:
                native_price: float = price
                native_currency: str = str(info.get("currency", "EUR")).upper()
                currency: str = native_currency

                if native_currency != "EUR":
                    rate: float | None = get_exchange_rate(native_currency, "EUR")
                    if rate:
                        price = price * rate
                        currency = "EUR"

                return Quotation(
                    price=price,
                    currency=currency,
                    timestamp=datetime.now(UTC),
                    native_price=native_price,
                    native_currency=native_currency,
                )

            logger.error(
                f"[data collectors] Could not retrieve price for ticker '{asset.yahoo_ticker}'."
            )
            return None

        except Exception as e:
            logger.error(
                f"[data collectors] Error fetching quotation for '{asset.yahoo_ticker}': {e}"
            )
            return None

    @staticmethod
    def _parse_float(info: dict[str, Any], key: str) -> float | None:
        """Parses a float from yfinance info, returning None for missing or near-zero ratios."""
        val: Any = info.get(key)
        if val is None:
            return None
        try:
            parsed_val: float = float(val)
            if (
                key
                in (
                    "priceToBook",
                    "trailingPE",
                    "forwardPE",
                    "marketCap",
                    "pegRatio",
                    "totalDebtToEquity",
                )
                and parsed_val < 0.01
            ):
                return None
            return parsed_val
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_pct(info: dict[str, Any], key: str) -> float | None:
        """Parses a ratio from yfinance info and converts it to a percentage (×100)."""
        val: Any = info.get(key)
        if val is None:
            return None
        try:
            return round(float(val) * 100.0, 4)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_str(info: dict[str, Any], key: str) -> str | None:
        """Parses a string value from yfinance info."""
        val: Any = info.get(key)
        return str(val) if val is not None else None

    @staticmethod
    def _parse_int(info: dict[str, Any], key: str) -> int | None:
        """Parses an integer value from yfinance info."""
        val: Any = info.get(key)
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    def get_details(
        self,
        asset: Asset,
        force_refresh: bool = False,
        db_path: str | Path | None = None,
    ) -> StockDetails | None:
        """Fetches fundamental metrics and valuation ratios for a stock asset, using SQLite cache.

        Args:
            asset: Asset instance representing the stock.
            force_refresh: If True, bypasses cache and forces live API fetch.
            db_path: Optional path to the SQLite database.

        Returns:
            A StockDetails instance containing fundamental metrics, or None on failure.
        """
        if not asset.yahoo_ticker:
            logger.error(
                f"[data collectors] No Yahoo ticker provided for stock asset '{asset.name}'."
            )
            return None

        cache_repo: SqliteOpportunityRepository | None = None
        asset_id: int | None = None
        resolved_db: Path = Path(db_path) if db_path else Path(DEFAULT_DB_PATH)

        if not force_refresh and resolved_db.exists():
            try:
                with get_db_context(str(resolved_db)) as conn:
                    initialize_database(conn)
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT id FROM assets WHERE yahoo_ticker = ?",
                        (asset.yahoo_ticker,),
                    )
                    row = cur.fetchone()
                    if row:
                        asset_id = int(row["id"])

                if asset_id is not None:
                    cache_repo = SqliteOpportunityRepository(db_path=resolved_db)
                    cached: ETFDetails | StockDetails | None = cache_repo.get_asset_fundamentals(
                        asset_id=asset_id,
                        asset_type="STOCK",
                        ttl_hours=get_settings().stock_cache_ttl_days * 24,
                    )
                    if cached is not None and isinstance(cached, StockDetails):
                        logger.info(
                            f"[data collectors] Using cached fundamentals for '{asset.yahoo_ticker}' "
                            f"(asset_id={asset_id})."
                        )
                        return cached
            except Exception as e:
                logger.warning(
                    f"[data collectors] Cache lookup failed for '{asset.yahoo_ticker}', "
                    f"falling back to live fetch: {e}"
                )

        try:
            ticker: yf.Ticker = yf.Ticker(asset.yahoo_ticker)
            info: dict[str, Any] = ticker.info

            if not info or not isinstance(info, dict):
                logger.error(
                    f"[data collectors] yfinance returned empty metadata for '{asset.yahoo_ticker}'."
                )
                return None

            dividend_rate: float | None = self._parse_float(
                info, "dividendRate"
            ) or self._parse_float(info, "trailingAnnualDividendRate")
            current_price: float | None = (
                self._parse_float(info, "currentPrice")
                or self._parse_float(info, "previousClose")
                or self._parse_float(info, "regularMarketPrice")
            )

            dividend_yield_pct: float | None = None
            if dividend_rate is not None and current_price is not None and current_price > 0:
                dividend_yield_pct = round((dividend_rate / current_price) * 100.0, 4)
            else:
                raw_div: float | None = self._parse_float(info, "dividendYield")
                if raw_div is not None:
                    dividend_yield_pct = round(raw_div, 4)

            report_currency: str | None = info.get("financialCurrency")
            quote_currency: str | None = info.get("currency")
            currencies_match: bool = (
                report_currency is not None
                and quote_currency is not None
                and report_currency.upper() == quote_currency.upper()
            )
            fcf_raw: float | None = self._parse_float(info, "freeCashflow")
            free_cashflow: float | None = fcf_raw if currencies_match else None
            pb_raw: float | None = self._parse_float(info, "priceToBook")
            price_to_book: float | None = pb_raw if currencies_match else None

            fifty_day_avg: float | None = self._parse_float(info, "fiftyDayAverage")
            raw_price: float | None = self._parse_float(info, "currentPrice") or self._parse_float(
                info, "regularMarketPrice"
            )
            if (
                raw_price is not None
                and fifty_day_avg is not None
                and fifty_day_avg > 0
                and abs(raw_price - fifty_day_avg) / fifty_day_avg > 0.50
            ):
                raw_price = self._parse_float(info, "regularMarketPrice") or self._parse_float(
                    info, "previousClose"
                )

            result: StockDetails = StockDetails(
                market_cap=self._parse_float(info, "marketCap"),
                pe_ratio=self._parse_float(info, "trailingPE"),
                forward_pe=self._parse_float(info, "forwardPE"),
                dividend_yield_pct=dividend_yield_pct,
                fifty_two_week_high=self._parse_float(info, "fiftyTwoWeekHigh"),
                fifty_two_week_low=self._parse_float(info, "fiftyTwoWeekLow"),
                fifty_two_week_change_pct=self._parse_pct(info, "52WeekChange"),
                fifty_day_average=fifty_day_avg,
                two_hundred_day_average=self._parse_float(info, "twoHundredDayAverage"),
                average_volume=self._parse_int(info, "averageVolume"),
                sector=self._parse_str(info, "sector"),
                industry=self._parse_str(info, "industry"),
                country=self._parse_str(info, "country"),
                price_to_book=price_to_book,
                peg_ratio=self._parse_float(info, "pegRatio"),
                beta=self._parse_float(info, "beta"),
                profit_margins_pct=self._parse_pct(info, "profitMargins"),
                gross_margins_pct=self._parse_pct(info, "grossMargins"),
                operating_margins_pct=self._parse_pct(info, "operatingMargins"),
                revenue_growth_pct=self._parse_pct(info, "revenueGrowth"),
                earnings_growth_pct=self._parse_pct(info, "earningsGrowth"),
                return_on_equity_pct=self._parse_pct(info, "returnOnEquity"),
                return_on_assets_pct=self._parse_pct(info, "returnOnAssets"),
                total_debt_to_equity=self._parse_float(info, "debtToEquity"),
                free_cashflow=free_cashflow,
                short_ratio=self._parse_float(info, "shortRatio"),
                target_mean_price=self._parse_float(info, "targetMeanPrice"),
                target_high_price=self._parse_float(info, "targetHighPrice"),
                target_low_price=self._parse_float(info, "targetLowPrice"),
                number_of_analyst_opinions=self._parse_int(info, "numberOfAnalystOpinions"),
                recommendation_key=self._parse_str(info, "recommendationKey"),
                eps_trailing_ttm=self._parse_float(info, "trailingEps"),
                eps_forward=self._parse_float(info, "forwardEps"),
                currency=self._parse_str(info, "currency"),
            )

            if cache_repo is not None and asset_id is not None:
                try:
                    cache_repo.upsert_asset_fundamentals(
                        asset_id=asset_id,
                        asset_type="STOCK",
                        details=result,
                    )
                except Exception as cache_err:
                    logger.warning(
                        f"[data collectors] Failed to populate fundamentals cache for "
                        f"'{asset.yahoo_ticker}': {cache_err}"
                    )

            return result
        except Exception as e:
            err_details: str = f"{type(e).__name__} - {e}"
            logger.error(
                f"[data collectors] yfinance exception while fetching '{asset.yahoo_ticker}': "
                f"{err_details}"
            )
            return None


class ETFProvider:
    """Hybrid data provider for ETFs combining yfinance market data and JustETF composition."""

    def __init__(
        self,
        justetf_client: Any | None = None,
        cache_repo: ETFCacheRepository | None = None,
        stock_provider: StockProvider | None = None,
    ) -> None:
        """Initializes the ETF provider with optional client and repository dependencies.

        JustETFClient is imported lazily inside __init__ to avoid a circular
        import between infra.just_etf and core.providers at module load time.
        """
        from infra.just_etf.just_etf_client import JustETFClient

        self.justetf_client: Any = justetf_client or JustETFClient()
        self.cache_repo: ETFCacheRepository = cache_repo or JsonETFCacheRepository()
        self._stock_provider: StockProvider = stock_provider or StockProvider()

    def get_price(self, asset: Asset) -> Quotation | None:
        """Delegates price fetching for an ETF asset to the stock provider."""
        return self._stock_provider.get_price(asset)

    @staticmethod
    def _yf_float(info: dict[str, Any], key: str) -> float | None:
        """Parses a float from a yfinance info dict, returning None on missing or invalid values."""
        val: Any = info.get(key)
        try:
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _yf_int(info: dict[str, Any], key: str) -> int | None:
        """Parses an int from a yfinance info dict, returning None on missing or invalid values."""
        val: Any = info.get(key)
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    def get_market_data(self, asset: Asset) -> ETFMarketData | None:
        """Fetches extended market data and moving averages for an ETF via yfinance.

        Args:
            asset: Asset instance representing the ETF.

        Returns:
            An ETFMarketData instance with pricing and volume metrics, or None on failure.
        """
        if not asset.yahoo_ticker:
            logger.error(
                f"[data collectors] No Yahoo ticker provided for ETF asset '{asset.name}'."
            )
            return None
        try:
            info: dict[str, Any] = yf.Ticker(asset.yahoo_ticker).info
            if not info or not isinstance(info, dict):
                return None

            price: float | None = (
                self._yf_float(info, "regularMarketPrice")
                or self._yf_float(info, "currentPrice")
                or self._yf_float(info, "previousClose")
            )
            currency: str | None = (
                str(info.get("currency", "EUR")).upper() if info.get("currency") else None
            )

            return ETFMarketData(
                price=price,
                native_currency=currency,
                just_etf_ticker=asset.just_etf_ticker,
                nav_price=self._yf_float(info, "navPrice"),
                fifty_two_week_high=self._yf_float(info, "fiftyTwoWeekHigh"),
                fifty_two_week_low=self._yf_float(info, "fiftyTwoWeekLow"),
                fifty_two_week_change_pct=self._yf_float(info, "fiftyTwoWeekChangePercent"),
                fifty_day_average=self._yf_float(info, "fiftyDayAverage"),
                two_hundred_day_average=self._yf_float(info, "twoHundredDayAverage"),
                average_volume=self._yf_int(info, "averageVolume"),
            )
        except Exception as e:
            logger.error(f"Error fetching market data for '{asset.yahoo_ticker}': {e}")
            return None

    def get_details(
        self,
        asset: Asset,
        force_refresh: bool = False,
        db_path: str | Path | None = None,
    ) -> ETFDetails | None:
        """Retrieves ETF composition and metadata via a three-layer fallback chain.

        Resolution order (each layer is skipped if force_refresh=True or unavailable):
        1. SQLite cache (asset_fundamentals table) — fastest, TTL controlled by settings.etf_cache_ttl_days.
        2. JSON file cache (JsonETFCacheRepository) — file-backed, TTL controlled by DEFAULT_ETF_CACHE_TTL_DAYS.
        3. Live JustETF scrape — result is written back to the JSON cache for future requests.

        Args:
            asset: Asset instance representing the ETF. Must have a valid ISIN.
            force_refresh: If True, bypasses all caches and triggers a live scrape.
            db_path: Optional path to the SQLite database for the SQLite cache layer.

        Returns:
            An ETFDetails instance containing holdings and breakdowns, or None if unavailable.
        """
        if not asset.isin:
            logger.error(f"[data collectors] No ISIN provided for ETF asset {asset.name}.")
            return None

        resolved_db: Path = Path(db_path) if db_path else Path(DEFAULT_DB_PATH)
        if not force_refresh and resolved_db.exists():
            try:
                asset_id: int | None = None
                with get_db_context(str(resolved_db)) as conn:
                    initialize_database(conn)
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT id FROM assets WHERE isin = ?",
                        (asset.isin,),
                    )
                    row = cur.fetchone()
                    if row:
                        asset_id = int(row["id"])

                if asset_id is not None:
                    db_cache_repo = SqliteOpportunityRepository(db_path=resolved_db)
                    db_cached = db_cache_repo.get_asset_fundamentals(
                        asset_id=asset_id,
                        asset_type="ETF",
                        ttl_hours=get_settings().etf_cache_ttl_days * 24,
                    )
                    if db_cached is not None and isinstance(db_cached, ETFDetails):
                        logger.info(
                            f"[data collectors] Using cached fundamentals for ETF '{asset.isin}' "
                            f"(asset_id={asset_id})."
                        )
                        return db_cached
            except Exception as e:
                logger.warning(
                    f"[data collectors] DB cache lookup failed for ETF '{asset.isin}', "
                    f"falling back to JustETF fetch: {e}"
                )

        if not force_refresh:
            cached_details: ETFDetails | None = self.cache_repo.get_etf_details(asset.isin)
            if cached_details is not None:
                return cached_details

        try:
            details: ETFDetails = self.justetf_client.get_etf_details(asset.isin)
            self.cache_repo.save_etf_details(asset.isin, details)
            return details
        except Exception as e:
            logger.warning(
                f"[data collectors] Failed to fetch ETF details for {asset.name} ({asset.isin}): {e}"
            )
            return None
