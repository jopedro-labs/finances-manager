"""Utility module for fetching real-time currency exchange rates using yfinance."""

from __future__ import annotations

import sys
from typing import Any

import yfinance as yf  # type: ignore[import-untyped]

from core.exceptions import ExchangeRateFetchError
from infra.logger import logger


def get_exchange_rate(from_currency: str, to_currency: str = "EUR") -> float | None:
    """Fetches the current exchange rate between two currencies via yfinance.

    Constructs the Yahoo Finance pair symbol (e.g. 'USDEUR=X') and reads the
    most recent closing price from the 1-day history. Returns 1.0 immediately
    if both currencies are the same.

    Args:
        from_currency: ISO 4217 source currency code (e.g. 'USD', 'DKK').
        to_currency: ISO 4217 target currency code. Defaults to 'EUR'.

    Returns:
        The exchange rate as a float (e.g. 0.92 for USD→EUR), or None if
        the rate cannot be retrieved.

    Raises:
        ExchangeRateFetchError: Logged internally — callers receive None on failure.
    """
    from_curr: str = from_currency.upper()
    to_curr: str = to_currency.upper()

    if from_curr == to_curr:
        return 1.0

    pair_symbol: str = f"{from_curr}{to_curr}=X"
    try:
        pair_ticker: yf.Ticker = yf.Ticker(pair_symbol)
        hist: Any = pair_ticker.history(period="1d")

        if not hist.empty:
            return float(hist["Close"].iloc[-1])

        err = ExchangeRateFetchError(
            f"[currency exchange] No history returned for exchange rate symbol '{pair_symbol}'."
        )
        logger.error(str(err))
        return None
    except Exception as e:
        err = ExchangeRateFetchError(
            f"[currency exchange] Error retrieving exchange rate for {from_curr}/{to_curr}: {e}"
        )
        logger.error(str(err), exception=e)
        return None


def get_usd_to_eur_rate() -> float | None:
    """Convenience wrapper that returns the current USD to EUR conversion rate.

    Returns:
        The USD/EUR exchange rate as a float, or None if unavailable.
    """
    return get_exchange_rate("USD", "EUR")


def main() -> None:
    """CLI execution entry point for currency exchange lookup."""
    if len(sys.argv) < 3:
        logger.error("[currency exchange] Currencies not provided.")
        logger.info(
            "[currency exchange] Usage: python3 -m core.currency_exchange <FROM_CURRENCY> <TO_CURRENCY>"
        )
        sys.exit(1)

    from_c: str = sys.argv[1].upper()
    to_c: str = sys.argv[2].upper()
    rate_val: float | None = get_exchange_rate(from_c, to_c)
    logger.info(f"[currency exchange] Exchange rate {from_c}/{to_c}: {rate_val}")


if __name__ == "__main__":
    main()
