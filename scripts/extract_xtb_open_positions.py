"""Script for extracting structured financial data from broker screenshots using Gemini Vision API.

Reads the source image from the local input/ directory.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from core_lib.logger import logger
from dotenv import load_dotenv
from google import genai
from google.genai import types

from config import get_settings
from core.exceptions import GeminiParsingError

load_dotenv()
settings = get_settings()
ROOT_DIR: Path = Path(__file__).resolve().parent.parent

LOCAL_SCREENSHOT_PATH: Path = ROOT_DIR / "input" / "xtb_screenshot.png"


def get_screenshot_path() -> Path:
    """Returns the path to the local XTB screenshot, exiting if not found."""
    if not LOCAL_SCREENSHOT_PATH.exists():
        logger.error(
            f"[extract with gemini] Screenshot not found at '{LOCAL_SCREENSHOT_PATH}'. "
            "Place xtb_screenshot.png in the input/ folder before running make snapshot."
        )
        sys.exit(1)
    logger.info(f"[extract with gemini] Using local screenshot: '{LOCAL_SCREENSHOT_PATH}'")
    return LOCAL_SCREENSHOT_PATH


def extract_data_from_screenshot(image_path: Path) -> dict[str, Any]:
    """Sends a broker screenshot to the Gemini Vision model and extracts portfolio positions,

    returning a structured dictionary matching the snapshot schema.
    """
    if not image_path.exists():
        raise FileNotFoundError(f"[extract with gemini] Image not found at {image_path.absolute()}")

    api_key = settings.gemini_api_key
    if not api_key:
        raise ValueError(
            "[extract with gemini] GEMINI_API_KEY is not configured in environment or .env."
        )

    portfolio_path = ROOT_DIR / "data" / "portfolio.json"
    portfolio_json = portfolio_path.read_text(encoding="utf-8") if portfolio_path.exists() else "{}"

    logger.info(
        f"[extract with gemini] Initializing Gemini client to process '{image_path.name}'..."
    )
    client = genai.Client(api_key=api_key)

    prompt = f"""You are a financial data extractor. Analyze this XTB broker screenshot showing open positions.

Use the portfolio reference below to match each visible position by its display name (xtb_name field)
and enrich with the correct yahoo_ticker, isin, asset_type, and native_currency.

PORTFOLIO REFERENCE:
{portfolio_json}

EXTRACTION RULES:
- Read every row in the open positions table
- Match each row to the portfolio reference using the asset name visible in the screenshot
- For each position extract:
  - xtb_name: the name exactly as displayed in XTB
  - yahoo_ticker: from portfolio reference
  - isin: from portfolio reference
  - asset_type: STOCK or ETF (from portfolio reference)
  - currency: native_currency from portfolio reference (USD, EUR, or DKK)
  - quantity: number of units held (read from screenshot)
  - average_buy_price_<currency>: average buy price in native currency (use currency suffix, e.g. average_buy_price_usd)
  - market_price_<currency>: current market price in native currency (use currency suffix)
  - market_value_eur: total value in EUR as shown in the "Value" column (sovereign — do not recalculate)
  - net_profit_eur: unrealised P&L in EUR as shown in the "Net Profit" column (sovereign — do not recalculate)
- Capture the EUR/USD exchange rate if visible in the screenshot; set null if not visible
- Today's date in YYYY-MM-DD format and current UTC timestamp

Return ONLY valid JSON, no markdown, no explanation:

{{
  "date": "YYYY-MM-DD",
  "timestamp": "YYYY-MM-DDTHH:MM:SSZ",
  "currencies_rate": {{"EURUSD": 1.05}},
  "holdings": [
    {{
      "xtb_name": "Core MSCI World",
      "yahoo_ticker": "EUNL.DE",
      "isin": "IE00B4L5Y983",
      "asset_type": "ETF",
      "currency": "EUR",
      "quantity": 7,
      "average_buy_price_eur": 130.995,
      "market_price_eur": 129.475,
      "market_value_eur": 906.33,
      "net_profit_eur": -10.64
    }}
  ]
}}"""

    try:
        with image_path.open("rb") as f:
            image_bytes = f.read()

        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt,
            ],
        )

        text_output = response.text
        if not text_output:
            raise GeminiParsingError(
                "[extract with gemini] Received empty response from Gemini API."
            )

        cleaned_text = text_output.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.startswith("```"):
            cleaned_text = cleaned_text[3:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
        cleaned_text = cleaned_text.strip()

        raw_data: Any = json.loads(cleaned_text)
        parsed_data: dict[str, Any] = dict(raw_data) if isinstance(raw_data, dict) else {}

        logger.success(
            f"[extract with gemini] Successfully extracted and parsed data from '{image_path.name}'."
        )
        return parsed_data

    except Exception as e:
        logger.error(f"[extract with gemini] Error during Gemini Vision extraction: {e}")
        raise GeminiParsingError(f"Failed to parse screenshot: {e}") from e


def main() -> None:
    """CLI entry point for standalone Gemini screenshot extraction."""
    try:
        target_image = get_screenshot_path()
        result = extract_data_from_screenshot(target_image)
        print(json.dumps(result, indent=2))
    except Exception as exc:
        logger.error(f"[extract with gemini] Execution failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
