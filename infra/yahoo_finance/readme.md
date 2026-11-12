# Yahoo Finance Client

Infrastructure client for fetching market data and asset details via [yfinance](https://github.com/ranaroussi/yfinance).

## Module structure

```
infra/yahoo_finance/
├── __init__.py               # Exports YahooFinanceClient, YahooFinanceError
└── yahoo_finance_client.py   # Client implementation + private helpers
```

## Classes

### `YahooFinanceClient`

Stateless client. Instantiate once and call any method.

```python
from infra.yahoo_finance import YahooFinanceClient

client = YahooFinanceClient()
```

### `YahooFinanceError`

Raised on any failure (network, missing data, invalid ticker). Always wraps the original exception via `from e`.

---

## Methods

### `get_quotation(ticker: str) -> Quotation`

Fetches the latest close price and currency for any ticker.

Uses `t.history(period="1d")` for the price and `t.info` for the currency.
Raises `YahooFinanceError` if history is empty, close price is missing, or currency cannot be determined.

**Example — `get_quotation("AAPL")`**

```python
{
    'price': 355.63,
    'currency': 'USD',
    'timestamp': '2026-11-11T21:06:34.650184+00:00',
    'native_price': 355.63,
    'native_currency': 'USD',
}
```

> Note: `price` and `native_price` are both the raw native price. Conversion to EUR is the caller's responsibility.

---

### `get_stock_details(ticker: str) -> StockDetails`

Fetches fundamental metrics, valuation ratios, and market data for a stock ticker via `t.info`.
Raises `YahooFinanceError` if `t.info` fails.

Percentage fields (margins, growth, yields) are scaled x100 from the raw yfinance decimals (e.g. `0.276` -> `27.6`).

**Example — `get_stock_details("AAPL")`**

```python
{
    'market_cap': 5168079831040.0,
    'pe_ratio': 39.60,
    'forward_pe': 33.70,
    'dividend_yield_pct': 31.0,          # raw: 0.31 -> scaled x100
    'fifty_two_week_high': 355.9,
    'fifty_two_week_low': 243.42,
    'fifty_two_week_change_pct': 27.44,  # raw: 0.2744 -> scaled x100
    'fifty_day_average': 337.27,
    'two_hundred_day_average': 299.78,
    'average_volume': 42821268,
    'sector': 'Technology',
    'industry': 'Consumer Electronics',
    'country': 'United States',
    'price_to_book': 46.11,
    'peg_ratio': 2.81,
    'beta': 1.089,
    'profit_margins_pct': 27.60,         # raw: 0.276 -> scaled x100
    'gross_margins_pct': 48.79,
    'operating_margins_pct': 33.01,
    'revenue_growth_pct': 11.70,
    'earnings_growth_pct': 14.10,
    'return_on_equity_pct': 142.26,
    'return_on_assets_pct': 25.87,
    'total_debt_to_equity': 84.29,
    'free_cashflow': 105658376192.0,
    'short_ratio': 3.59,
    'target_mean_price': 344.62,
    'target_high_price': 425.0,
    'target_low_price': 250.0,
    'number_of_analyst_opinions': 40,
    'recommendation_key': 'buy',
    'eps_trailing_ttm': 8.98,
    'eps_forward': 10.55,
    'currency': 'USD',
}
```

**Raw `t.info` fields captured -> model field mapping**

| `t.info` key | Model field | Scale |
|---|---|---|
| `marketCap` | `market_cap` | — |
| `trailingPE` | `pe_ratio` | — |
| `forwardPE` | `forward_pe` | — |
| `dividendYield` | `dividend_yield_pct` | x100 |
| `fiftyTwoWeekHigh` | `fifty_two_week_high` | — |
| `fiftyTwoWeekLow` | `fifty_two_week_low` | — |
| `52WeekChange` | `fifty_two_week_change_pct` | x100 |
| `fiftyDayAverage` | `fifty_day_average` | — |
| `twoHundredDayAverage` | `two_hundred_day_average` | — |
| `averageVolume` | `average_volume` | — |
| `sector` | `sector` | — |
| `industry` | `industry` | — |
| `country` | `country` | — |
| `priceToBook` | `price_to_book` | — |
| `pegRatio` | `peg_ratio` | — |
| `beta` | `beta` | — |
| `profitMargins` | `profit_margins_pct` | x100 |
| `grossMargins` | `gross_margins_pct` | x100 |
| `operatingMargins` | `operating_margins_pct` | x100 |
| `revenueGrowth` | `revenue_growth_pct` | x100 |
| `earningsGrowth` | `earnings_growth_pct` | x100 |
| `returnOnEquity` | `return_on_equity_pct` | x100 |
| `returnOnAssets` | `return_on_assets_pct` | x100 |
| `debtToEquity` | `total_debt_to_equity` | — |
| `freeCashflow` | `free_cashflow` | — |
| `shortRatio` | `short_ratio` | — |
| `targetMeanPrice` | `target_mean_price` | — |
| `targetHighPrice` | `target_high_price` | — |
| `targetLowPrice` | `target_low_price` | — |
| `numberOfAnalystOpinions` | `number_of_analyst_opinions` | — |
| `recommendationKey` | `recommendation_key` | — |
| `trailingEps` | `eps_trailing_ttm` | — |
| `forwardEps` | `eps_forward` | — |
| `currency` | `currency` | — |

**Notable raw fields available but not captured**

| `t.info` key | Example value | Notes |
|---|---|---|
| `currentPrice` | 355.63 | Alternative price source (no history call needed) |
| `targetMedianPrice` | 352.50 | Analyst median target (only mean/high/low captured) |
| `trailingPegRatio` | 2.81 | Trailing PEG vs forward `pegRatio` |
| `currentRatio` | 1.023 | Liquidity ratio |
| `quickRatio` | 0.827 | Adjusted liquidity ratio |
| `totalCash` | 56722001920 | Cash on hand |
| `totalDebt` | 94478999552 | Total debt |
| `ebitda` | 171486003200 | EBITDA |
| `ebitdaMargins` | 0.358 | EBITDA margin |
| `payoutRatio` | 0.118 | Dividend payout ratio |
| `revenuePerShare` | 32.66 | Revenue per share |
| `heldPercentInsiders` | 0.0166 | Insider ownership % |
| `heldPercentInstitutions` | 0.6699 | Institutional ownership % |
| `sharesShort` | 144791472 | Absolute short interest |
| `averageAnalystRating` | "2.2 - Buy" | Human-readable consensus |
| `longBusinessSummary` | "Apple Inc. designs..." | Company description |

---

### `get_etf_market_data(ticker: str) -> ETFMarketData`

Fetches market price, currency, NAV, moving averages and volume for an ETF ticker.
Uses `_fetch_ticker_market_data` internally (single `yf.Ticker` call for both `t.info` and `t.history`).
Raises `YahooFinanceError` if `t.info` fails, history is empty, price is missing, or currency is absent.

**Example — `get_etf_market_data("VWCE.DE")`**

```python
{
    'price': 170.92,
    'native_currency': 'EUR',
    'just_etf_ticker': None,             # populated by justETF client, not Yahoo
    'nav_price': 187.42,
    'fifty_two_week_high': 173.96,
    'fifty_two_week_low': 139.2,
    'fifty_two_week_change_pct': None,   # see known limitation below
    'fifty_day_average': 169.40,
    'two_hundred_day_average': 160.35,
    'average_volume': 291597,
}
```

**Raw `t.info` fields captured -> model field mapping**

| `t.info` key | Model field | Notes |
|---|---|---|
| `navPrice` | `nav_price` | — |
| `fiftyTwoWeekHigh` | `fifty_two_week_high` | — |
| `fiftyTwoWeekLow` | `fifty_two_week_low` | — |
| `52WeekChange` | `fifty_two_week_change_pct` | See known limitation |
| `fiftyDayAverage` | `fifty_day_average` | — |
| `twoHundredDayAverage` | `two_hundred_day_average` | — |
| `averageVolume` | `average_volume` | — |

**Notable raw fields available but not captured**

| `t.info` key | Example value | Notes |
|---|---|---|
| `netAssets` / `totalAssets` | 88843731000 | Fund size in EUR |
| `fundFamily` | "Vanguard Group (Ireland) Limited" | Fund manager |
| `fundInceptionDate` | 1563840000 (epoch) | Launch date |
| `legalType` | "Exchange Traded Fund" | Fund legal type |
| `fiftyTwoWeekChangePercent` | 15.013 | See known limitation |

---

## Known limitations

### `fifty_two_week_change_pct` always `None` for ETFs

Yahoo Finance uses different key names depending on the instrument type:

| Instrument | Key in `t.info` |
|---|---|
| Stock | `52WeekChange` |
| ETF | `fiftyTwoWeekChangePercent` |

The client currently reads only `52WeekChange`, so ETF 52-week change is always `None`.
Fix: fall back to `fiftyTwoWeekChangePercent` when `52WeekChange` is absent.

### `Quotation.price` is in native currency, not EUR

`get_quotation` populates `price` with the native trading price (e.g. USD for AAPL).
The `Quotation` model docstring states `price` should be "converted to EUR" — conversion is left to the caller.

---

## Private helpers

### `_fetch_ticker_market_data(ticker) -> tuple[float, str, dict]`

Shared helper used by `get_quotation` and `get_etf_market_data`. Returns `(price, currency, info)` from a single `yf.Ticker` instance, avoiding duplicate HTTP calls.

### `_safe_float(val, scale=1.0) -> float | None`
### `_safe_int(val) -> int | None`
### `_safe_str(val) -> str | None`

Module-level parsing helpers. Return `None` for `None` or empty string inputs. `_safe_float` accepts an optional `scale` multiplier used to convert yfinance decimals to percentages (e.g. `scale=100.0`).
