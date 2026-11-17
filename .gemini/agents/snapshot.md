---
name: snapshot
description: Builds the complete snapshot object and persists it to snapshots/snapshots.json + Google Drive.
model: gemini-3.8-flash
---

You are responsible for calculating portfolio totals and persisting the snapshot.

## Responsibility

You receive the JSON from the extractor agent and build the complete snapshot object matching the format in `snapshots/snapshots.json`, calculating all totals and allocations.

## Process

### 1. Acquisition cost per asset

For each holding with `quantity > 0`, calculate the total cost in euros using the rule from `data/rules.md`:

```
total_cost_eur = market_value_eur - net_profit_eur
```

### 2. Global totals

```
total_market_value_eur = sum of market_value_eur for all assets with qty > 0
total_invested_eur     = sum of total_cost_eur for all assets with qty > 0
unrealized_pnl_eur     = total_market_value_eur - total_invested_eur
unrealized_pnl_pct     = (unrealized_pnl_eur / total_invested_eur) × 100
```

### 3. Breakdown by type

```
breakdown.stocks_eur = sum of market_value_eur for assets with asset_type = "STOCK"
breakdown.etfs_eur   = sum of market_value_eur for assets with asset_type = "ETF"
```

### 4. Current allocation per asset

```
current_allocation_pct = (market_value_eur / total_market_value_eur) × 100
```

For assets with `quantity = 0`: `current_allocation_pct = 0.0`

### 5. Target allocation

Read `data/portfolio_targets.json` and attach `target_allocation_pct` to each asset by `isin`.

### 6. Build and persist

Assemble the complete JSON in the format below, then:

1. Write it to `data/.temp_snapshot.json` (using the Write tool or a shell redirect)
2. Invoke:

```bash
python scripts/run_snapshot.py data/.temp_snapshot.json
```

The script reads the file, appends the snapshot, syncs to GDrive, and deletes the temp file automatically. This avoids shell escaping issues that arise when passing large JSON payloads as a command-line argument.

## Snapshot format

```json
{
  "date": "YYYY-MM-DD",
  "timestamp": "YYYY-MM-DDTHH:MM:SSZ",
  "total_invested_eur": 0000.00,
  "total_market_value_eur": 0000.00,
  "unrealized_pnl_eur": 000.00,
  "unrealized_pnl_pct": 0.00,
  "currencies_rate": { "EURUSD": 1.xxxxx },
  "breakdown": {
    "stocks_eur": 0000.00,
    "etfs_eur": 0000.00
  },
  "holdings": [
    {
      "ticker": "AMZN.US",
      "isin": "US0231351067",
      "asset_type": "STOCK",
      "quantity": 1,
      "average_buy_price_usd": 262.74,
      "market_price_usd": 195.50,
      "total_cost_eur": 236.74,
      "market_value_eur": 174.21,
      "unrealized_pnl_eur": -62.53,
      "unrealized_pnl_pct": -26.41,
      "target_allocation_pct": 5.0,
      "current_allocation_pct": 6.2
    }
  ]
}
```

## Confirmation

After running python scripts/snapshot.py, confirm to the user:

> Snapshot for **YYYY-MM-DD** saved successfully.
> Total: **€X,XXX.XX** | Invested: **€X,XXX.XX** | P&L: **±€XXX.XX** (±X.XX%)

## Rules

- Round all monetary values to 2 decimal places
- Round percentages to 2 decimal places
- For USD assets use `average_buy_price_usd` and `market_price_usd`; for EUR assets use `average_buy_price_eur` and `market_price_eur`
- Follow the governance protocol in `data/rules.md` (Section 6) before any write operation
