"""
Extracts position data from an XTB screenshot via Gemini Vision API,
calculates snapshot totals and allocations, writes data/.temp_snapshot.json,
and triggers scripts/snapshot.py for persistence and GDrive sync.

Usage:
    python scripts/extract_with_gemini.py [image_path_or_dir]

If no argument is given, uses the most recent image in input/.
"""

from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from google import genai
from google.genai import types
from google.genai.errors import APIError
from pydantic import BaseModel

from config import DATA_DIR, INPUT_DIR, ROOT_DIR, get_settings
from infra.logger import logger

# ---------------------------------------------------------------------------
# Pydantic schemas for Gemini structured output
# ---------------------------------------------------------------------------


class ExtractedHolding(BaseModel):
    xtb_name: str
    quantity: float
    market_price: float
    market_value_eur: float
    net_profit_eur: float


class ExtractedSnapshot(BaseModel):
    eurusd_rate: float | None = None
    holdings: list[ExtractedHolding]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_latest_image(input_dir: Path) -> Path:
    patterns = ["*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG"]
    files = [f for p in patterns for f in input_dir.glob(p)]
    if not files:
        logger.error(f"[gemini extractor]No image files found in '{input_dir}'.")
        logger.info(
            "[gemini extractor] Please place an XTB Open Positions screenshot inside the 'input/' folder."
        )
        sys.exit(1)
    return max(files, key=lambda f: f.stat().st_mtime)


def load_json(filepath: Path) -> dict[str, Any]:
    if filepath.exists():
        with open(filepath, encoding="utf-8") as f:
            return cast(dict[str, Any], json.load(f))
    return {}


def round2(value: float) -> float:
    return round(value, 2)


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------


def extract_from_image(image_path: Path, client: genai.Client, model: str) -> ExtractedSnapshot:
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"

    prompt = """
    Carefully analyse this XTB 'Open Positions' screenshot.
    For each position row in the table extract:
    - xtb_name: the instrument name exactly as displayed in XTB (e.g. "Amazon", "Defense", "Uranium and Nuclear Technlgs")
    - quantity (Volume column)
    - market_price (current price in the asset's native currency)
    - market_value_eur (Value column in EUR)
    - net_profit_eur (Net Profit column in EUR)

    Also capture the EURUSD exchange rate if visible anywhere in the interface (null if not visible).
    """

    logger.info(f"[gemini extractor] Sending image to Gemini Vision ({model})...")
    try:
        response = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ExtractedSnapshot,
                temperature=0.1,
            ),
        )
    except APIError as e:
        logger.error("[gemini extractor] Gemini API error during extraction", exception=e)
        sys.exit(1)

    if not response.parsed:
        logger.error("[gemini extractor] Gemini returned an empty or unparseable response.")
        sys.exit(1)

    return cast(ExtractedSnapshot, response.parsed)


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def build_snapshot(extracted: ExtractedSnapshot) -> dict[str, Any]:
    portfolio_meta = load_json(DATA_DIR / "portfolio.json")
    portfolio_targets = load_json(DATA_DIR / "portfolio_targets.json")

    meta_by_name = {
        item["xtb_name"]: item for item in portfolio_meta.get("assets", []) if "xtb_name" in item
    }
    target_by_isin = {
        item["isin"]: item.get("target_allocation_pct", 0.0)
        for item in portfolio_targets.get("assets", [])
        if "isin" in item
    }
    target_by_ticker = {
        item["ticker"]: item.get("target_allocation_pct", 0.0)
        for item in portfolio_targets.get("assets", [])
        if "ticker" in item
    }

    now = datetime.datetime.now(datetime.UTC)
    current_date = now.strftime("%Y-%m-%d")
    current_timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build active holdings from extracted data
    holdings: list[dict[str, Any]] = []
    processed_tickers: set[str] = set()

    for item in extracted.holdings:
        meta: dict[str, Any] = meta_by_name.get(item.xtb_name, {})
        ticker = meta.get("ticker", item.xtb_name)
        processed_tickers.add(ticker)

        currency = meta.get("currency", "EUR")
        price_key = f"market_price_{currency.lower()}"
        buy_key = f"average_buy_price_{currency.lower()}"
        isin = meta.get("isin", "")

        total_cost_eur = round2(item.market_value_eur - item.net_profit_eur)
        unrealized_pnl_eur = round2(item.net_profit_eur)
        unrealized_pnl_pct = round2(
            (unrealized_pnl_eur / total_cost_eur * 100) if total_cost_eur else 0.0
        )

        target_alloc = target_by_isin.get(isin) or target_by_ticker.get(ticker, 0.0)

        holdings.append(
            {
                "ticker": ticker,
                "isin": isin,
                "asset_type": meta.get("asset_type", "STOCK"),
                "currency": currency,
                "yahoo_ticker": meta.get("yahoo_ticker", ticker.split(".")[0]),
                "quantity": item.quantity,
                buy_key: meta.get(buy_key, meta.get("average_buy_price", 0.0)),
                price_key: item.market_price,
                "total_cost_eur": total_cost_eur,
                "market_value_eur": round2(item.market_value_eur),
                "unrealized_pnl_eur": unrealized_pnl_eur,
                "unrealized_pnl_pct": unrealized_pnl_pct,
                "target_allocation_pct": target_alloc,
                "current_allocation_pct": 0.0,  # filled after total is known
            }
        )

    # Add watchlist items (qty = 0) not present in the screenshot
    for target_item in portfolio_targets.get("assets", []):
        ticker = target_item.get("ticker")
        if not ticker or ticker in processed_tickers:
            continue
        watchlist_meta: dict[str, Any] = next(
            (item for item in portfolio_meta.get("assets", []) if item.get("ticker") == ticker), {}
        )
        currency = watchlist_meta.get("currency", "EUR")
        buy_key = f"average_buy_price_{currency.lower()}"
        price_key = f"market_price_{currency.lower()}"
        isin = target_item.get("isin", watchlist_meta.get("isin", ""))

        holdings.append(
            {
                "ticker": ticker,
                "isin": isin,
                "asset_type": watchlist_meta.get("asset_type", "STOCK"),
                "currency": currency,
                "yahoo_ticker": watchlist_meta.get("yahoo_ticker", ticker.split(".")[0]),
                "quantity": 0,
                buy_key: 0.0,
                price_key: 0.0,
                "total_cost_eur": 0.0,
                "market_value_eur": 0.0,
                "unrealized_pnl_eur": 0.0,
                "unrealized_pnl_pct": 0.0,
                "target_allocation_pct": target_item.get("target_allocation_pct", 0.0),
                "current_allocation_pct": 0.0,
            }
        )

    # Calculate portfolio totals from active holdings only
    active = [h for h in holdings if h["quantity"] > 0]
    total_market_value_eur = round2(sum(h["market_value_eur"] for h in active))
    total_invested_eur = round2(sum(h["total_cost_eur"] for h in active))
    unrealized_pnl_eur = round2(
        sum(h["market_value_eur"] for h in active) - sum(h["total_cost_eur"] for h in active)
    )
    unrealized_pnl_pct = round2(
        (unrealized_pnl_eur / total_invested_eur * 100) if total_invested_eur else 0.0
    )

    stocks_eur = round2(sum(h["market_value_eur"] for h in active if h["asset_type"] == "STOCK"))
    etfs_eur = round2(sum(h["market_value_eur"] for h in active if h["asset_type"] == "ETF"))

    # Fill current_allocation_pct now that total is known
    for h in holdings:
        if h["quantity"] > 0 and total_market_value_eur > 0:
            h["current_allocation_pct"] = round2(
                h["market_value_eur"] / total_market_value_eur * 100
            )

    return {
        "date": current_date,
        "timestamp": current_timestamp,
        "total_invested_eur": total_invested_eur,
        "total_market_value_eur": total_market_value_eur,
        "unrealized_pnl_eur": unrealized_pnl_eur,
        "unrealized_pnl_pct": unrealized_pnl_pct,
        "currencies_rate": {"EURUSD": extracted.eurusd_rate},
        "breakdown": {
            "stocks_eur": stocks_eur,
            "etfs_eur": etfs_eur,
        },
        "holdings": holdings,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg:
        image_path = Path(arg)
        if image_path.is_dir():
            image_path = get_latest_image(image_path)
    else:
        image_path = get_latest_image(INPUT_DIR)

    if not image_path.exists():
        logger.error(f"[gemini extractor] File not found: '{image_path}'.")
        sys.exit(1)

    logger.info(f"[gemini extractor] Processing image: {image_path.name}")

    settings = get_settings()
    if not settings.gemini_api_key:
        logger.error("[gemini extractor] GEMINI_API_KEY is not set in .env.")
        sys.exit(1)

    client = genai.Client(api_key=settings.gemini_api_key)
    extracted = extract_from_image(image_path, client, settings.gemini_model)

    logger.info(f"[gemini extractor] Extracted {len(extracted.holdings)} position(s).")
    for h in extracted.holdings:
        logger.info(
            f"  {h.xtb_name:30} qty={h.quantity}  value={h.market_value_eur:.2f} EUR  pnl={h.net_profit_eur:.2f} EUR"
        )

    snapshot = build_snapshot(extracted)

    temp_path = DATA_DIR / ".temp_snapshot.json"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    logger.info(f"[gemini extractor] Snapshot written to '{temp_path}'. Triggering snapshot.py...")

    result = subprocess.run(
        [sys.executable, str(ROOT_DIR / "scripts" / "snapshot.py"), str(temp_path)],
        check=False,
    )

    if result.returncode != 0:
        logger.error("[gemini extractor] snapshot.py failed. Check logs above.")
        sys.exit(1)

    logger.success(
        f"[gemini extractor] Snapshot for {snapshot['date']} saved. "
        f"Total: €{snapshot['total_market_value_eur']:,.2f} | "
        f"Invested: €{snapshot['total_invested_eur']:,.2f} | "
        f"P&L: €{snapshot['unrealized_pnl_eur']:+,.2f} ({snapshot['unrealized_pnl_pct']:+.2f}%)"
    )


if __name__ == "__main__":
    main()
