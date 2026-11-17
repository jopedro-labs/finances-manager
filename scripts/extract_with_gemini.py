"""Script for extracting structured financial data from broker screenshots using Gemini Vision API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from config import get_settings
from core.exceptions import GeminiParsingError
from infra.logger import logger

settings = get_settings()


def extract_data_from_screenshot(image_path: Path) -> dict[str, Any]:
    """Sends a broker screenshot to the Gemini Vision model and extracts portfolio positions.

    Args:
        image_path: Path to the local screenshot image file.

    Returns:
        A dictionary containing extracted asset positions and account metrics.

    Raises:
        GeminiParsingError: If extraction or API communication fails.
    """
    if not image_path.exists():
        raise FileNotFoundError(f"[extract with gemini] Image not found at {image_path.absolute()}")

    api_key = settings.gemini_api_key
    if not api_key:
        raise ValueError("[extract with gemini] GEMINI_API_KEY is not configured in environment or .env.")

    logger.info(f"[extract with gemini] Initializing Gemini client to process '{image_path.name}'...")
    client = genai.Client(api_key=api_key)

    prompt = (
        "Analyze this brokerage platform screenshot (XTB or similar). "
        "Extract all open positions, including asset name, ticker/ISIN if visible, "
        "quantity held, average buy price, current market price, and total profit/loss. "
        "Return the output as a valid structured JSON format."
    )

    try:
        with image_path.open("rb") as f:
            image_bytes = f.read()

        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/png",
                ),
                prompt,
            ],
        )

        text_output = response.text
        if not text_output:
            raise GeminiParsingError("[extract with gemini] Received empty response from Gemini API.")

        logger.success(f"[extract with gemini] Successfully extracted data from '{image_path.name}'.")
        return {"raw_extraction": text_output, "source_image": image_path.name}

    except Exception as e:
        logger.error(f"[extract with gemini] Error during Gemini Vision extraction: {e}")
        raise GeminiParsingError(f"Failed to parse screenshot: {e}") from e


def main() -> None:
    """CLI entry point for Gemini screenshot extraction."""
    target_image = Path("input/xtb_screenshot.png")
    try:
        result = extract_data_from_screenshot(target_image)
        print(result)
    except Exception as exc:
        logger.error(f"[extract with gemini] Execution failed: {exc}")


if __name__ == "__main__":
    main()