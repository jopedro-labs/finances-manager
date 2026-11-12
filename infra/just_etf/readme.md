# JustETF Client

Infrastructure client for scraping ETF holdings, sector and country exposures, TER, and fund metadata from [JustETF](https://www.justetf.com) profile pages.

## Module structure

```
infra/just_etf/
├── __init__.py           # Exports JustETFClient, JustETFScrapeError
└── just_etf_client.py    # Client implementation + private parsers
```

## Classes

### `JustETFClient`

HTTP scraping client. Instantiate once and reuse — the session and retry adapter are shared across calls.

```python
from infra.just_etf import JustETFClient

client = JustETFClient()
```

Constructor accepts optional `timeout` (default `10.0s`) and `max_retries` (default `3`).

### `JustETFScrapeError`

Raised on any failure (network error, HTTP error, parse failure). Always wraps the original exception via `from e`.

---

## Methods

### `get_etf_details(isin: str) -> ETFDetails`

Fetches and parses a complete ETF profile from JustETF for the given ISIN.

Returns an `ETFDetails` domain object containing holdings, sector breakdown, country breakdown, TER, and fund metadata.

Raises `JustETFScrapeError` on network failure, HTTP error, or parse failure.

**Example — `get_etf_details("IE00B3RBWM25")` (Vanguard FTSE All-World UCITS ETF)**

```python
ETFDetails(
    holdings=[
        Holding(name='NVIDIA Corp.',      isin='US67066G1040', weight_pct=5.01,  just_etf_ticker=None),
        Holding(name='Apple',             isin='US0378331005', weight_pct=4.52,  just_etf_ticker=None),
        Holding(name='Microsoft Corp',    isin='US5949181045', weight_pct=3.58,  just_etf_ticker=None),
        Holding(name='Amazon.com, Inc.',  isin='US0231351067', weight_pct=2.27,  just_etf_ticker=None),
        Holding(name='Alphabet, Inc. A',  isin='US02079K3059', weight_pct=1.91,  just_etf_ticker=None),
        # ... up to 10 top holdings
    ],
    sector_breakdown=[
        SectorExposure(sector_name='Technology',  weight_pct=38.27),
        SectorExposure(sector_name='Finance',     weight_pct=17.87),
        SectorExposure(sector_name='Industrials', weight_pct=8.98),
        SectorExposure(sector_name='Healthcare',  weight_pct=8.04),
        SectorExposure(sector_name='Other',       weight_pct=26.84),
    ],
    country_breakdown=[
        CountryExposure(country_name='United States',   weight_pct=60.33),
        CountryExposure(country_name='Japan',           weight_pct=6.04),
        CountryExposure(country_name='Taiwan',          weight_pct=3.53),
        CountryExposure(country_name='United Kingdom',  weight_pct=3.16),
        CountryExposure(country_name='Other',           weight_pct=26.94),
    ],
    ter_pct=0.14,
    inception_date='22 May 2012',
    fund_size_eur_m=23794.0,
    holdings_count=3797,
    replication='Physical',
    distribution_policy='Distributing',
    index_name='FTSE All-World',
    fund_currency='USD',
    volatility_1y_pct=10.96,
)
```

**`ETFDetails` field reference**

| Field | Type | Description |
|---|---|---|
| `holdings` | `list[Holding]` | Top holdings (up to 10), each with name, ISIN, and weight % |
| `sector_breakdown` | `list[SectorExposure]` | Sector allocation — name + weight % |
| `country_breakdown` | `list[CountryExposure]` | Country/region allocation — name + weight % |
| `ter_pct` | `float \| None` | Total Expense Ratio as a percentage (e.g. `0.14` = 0.14%) |
| `inception_date` | `str \| None` | Fund launch date as a string (e.g. `"22 May 2012"`) |
| `fund_size_eur_m` | `float \| None` | Fund AUM in EUR millions |
| `holdings_count` | `int \| None` | Total number of holdings in the fund |
| `replication` | `str \| None` | Replication method (e.g. `"Physical"`, `"Swap-based"`) |
| `distribution_policy` | `str \| None` | `"Distributing"` or `"Accumulating"` |
| `index_name` | `str \| None` | Benchmark index tracked (e.g. `"FTSE All-World"`) |
| `fund_currency` | `str \| None` | Base currency of the fund (e.g. `"USD"`) |
| `volatility_1y_pct` | `float \| None` | 1-year volatility as a percentage |

**`Holding` field reference**

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Holding name as displayed on JustETF |
| `isin` | `str` | ISIN extracted from the holding row anchor href |
| `weight_pct` | `float` | Portfolio weight as a percentage |
| `just_etf_ticker` | `str \| None` | Always `None` — populated externally if needed |

> Note: holdings without a valid ISIN are silently skipped to comply with the `Holding.isin: str` type contract.

---

## Private parsers

### `_parse_fund_metadata(soup) -> dict[str, Any]`

Extracts fund-level metadata from the full page text using regex patterns anchored to label/value pairs separated by newlines. Fields: `inception_date`, `replication`, `distribution_policy`, `index_name`, `fund_currency`, `fund_size_eur_m`, `holdings_count`, `volatility_1y_pct`.

### `_parse_holdings(soup) -> list[Holding]`

Three-level fallback strategy:
1. `data-testid` attribute containing `"top-holdings_row"`
2. `<table id="top-holdings">`
3. Heuristic: any table whose text contains `"holding"` but not `"sector"` or `"country"`

### `_parse_sectors(soup) -> list[SectorExposure]`

Three-level fallback strategy:
1. `data-testid` attribute containing `"sector"` and `"row"`
2. `<div id="sectors">`
3. Heuristic: any table whose text contains `"sector"` but not `"country"`

### `_parse_countries(soup) -> list[CountryExposure]`

Three-level fallback strategy:
1. `data-testid` attribute containing `"countr"` and `"row"`
2. `<div id="countries">`
3. Heuristic: any table whose text contains `"country"`, `"countries"`, or `"region"` but not `"sector"`

### `_parse_ter(soup) -> float | None`

DOM-scoped search: finds the TER label node, searches its `parent.parent` scope for a percentage value. Falls back to a global text search if no match is found in the scoped DOM.

### `_extract_isin_from_element(element: Tag) -> str`

Searches anchor `href` attributes within the element for an ISIN pattern (`[A-Z]{2}[A-Z0-9]{9}\d`). Falls back to raw HTML string search. Returns empty string if not found.

---

## HTTP behaviour

- Uses a `requests.Session` with a `urllib3.Retry` adapter: retries on HTTP 429, 500, 502, 503, 504 with `backoff_factor=1.0`
- Handles `429 Retry-After` header explicitly: sleeps for the indicated duration then retries once before letting the retry adapter take over
- Default `User-Agent` mimics Chrome on macOS to avoid bot detection

---

## Known limitations

### `inception_date` is a raw string, not a date

The value is captured directly from the page text (e.g. `"22 May 2012"`). No parsing to `datetime.date` is performed. Callers needing a structured date must parse it themselves.

### `index_name` regex is fragile

The pattern `r"Index\s*\n([^\n]+)"` is generic and could match unrelated occurrences of "Index" if JustETF restructures the page. A more robust pattern would anchor to `"Benchmark Index"`.

### `just_etf_ticker` is always `None`

`Holding.just_etf_ticker` is populated as `None` by this client. The JustETF ticker symbol is not scraped from the holdings table — it must be supplied externally if needed.
