"""Script for extracting structured financial data from broker screenshots using Gemini Vision API,

fetching the source image strictly and exclusively from the configured Google Drive folder ID.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

from core_lib.logger import logger
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from config import get_settings
from core.exceptions import GeminiParsingError

load_dotenv()
settings = get_settings()
ROOT_DIR: Path = Path(__file__).resolve().parent.parent


def download_screenshot_from_gdrive() -> Path:
    """Downloads the XTB screenshot image strictly from the folder ID

    defined by GDRIVE_XTB_OPEN_POSITIONS_FOLDER_ID.
    """
    folder_id = settings.gdrive_xtb_open_positions_folder_id

    if not folder_id:
        logger.error("[extract with gemini] GDRIVE_XTB_OPEN_POSITIONS_FOLDER_ID is not configured in .env.")
        sys.exit(1)

    logger.info(f"[extract with gemini] Connecting to Google Drive folder ID: {folder_id}...")

    token_path = ROOT_DIR / "secrets" / "token.json"
    if not token_path.exists():
        logger.error(f"[extract with gemini] OAuth token not found at {token_path}")
        sys.exit(1)

    try:
        creds = Credentials.from_authorized_user_file(
            str(token_path),
            scopes=["https://www.googleapis.com/auth/drive.readonly"],
        )
        if not creds.valid and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
        drive_service = build("drive", "v3", credentials=creds)

        input_dir = Path("input")
        input_dir.mkdir(parents=True, exist_ok=True)
        local_image_path = input_dir / "xtb_screenshot.png"

        logger.info(f"[extract with gemini] Searching for 'xtb_screenshot.png' strictly inside folder ID {folder_id}...")

        # Pesquisa restrita estritamente e unicamente à pasta configurada
        query = f"'{folder_id}' in parents and name = 'xtb_screenshot.png' and trashed = false"
        results = drive_service.files().list(
            q=query,
            spaces="drive",
            fields="files(id, name)"
        ).execute()
        files = results.get("files", [])

        if not files:
            logger.error(
                f"[extract with gemini] File 'xtb_screenshot.png' not found inside folder ID {folder_id}. "
                "Verify if the folder/file is shared with the service account."
            )
            sys.exit(1)

        file_id = files[0]["id"]
        logger.info(f"[extract with gemini] Found 'xtb_screenshot.png' (ID: {file_id}). Downloading...")

        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        with open(local_image_path, "wb") as f:
            f.write(fh.getvalue())

        logger.success("[extract with gemini] Successfully downloaded screenshot from target Google Drive folder.")
        return local_image_path

    except Exception as e:
        logger.error(f"[extract with gemini] Failed to download screenshot from Google Drive: {e}")
        sys.exit(1)


def extract_data_from_screenshot(image_path: Path) -> dict[str, Any]:
    """Sends a broker screenshot to the Gemini Vision model and extracts portfolio positions,

    returning a structured dictionary.
    """
    if not image_path.exists():
        raise FileNotFoundError(f"[extract with gemini] Image not found at {image_path.absolute()}")

    api_key = settings.gemini_api_key
    if not api_key:
        raise ValueError(
            "[extract with gemini] GEMINI_API_KEY is not configured in environment or .env."
        )

    logger.info(
        f"[extract with gemini] Initializing Gemini client to process '{image_path.name}'..."
    )
    client = genai.Client(api_key=api_key)

    prompt = (
        "Analyze this brokerage platform screenshot (XTB or similar). "
        "Extract all open positions, including asset name, ticker/ISIN if visible, "
        "quantity held, average buy price, current market price, and total profit/loss. "
        "Return the output as a valid structured JSON format without markdown wrappers if possible, "
        "or standard JSON."
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
            raise GeminiParsingError(
                "[extract with gemini] Received empty response from Gemini API."
            )

        cleaned_text = text_output.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
        cleaned_text = cleaned_text.strip()

        parsed_data = json.loads(cleaned_text)

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
        target_image = download_screenshot_from_gdrive()
        result = extract_data_from_screenshot(target_image)
        print(result)
    except Exception as exc:
        logger.error(f"[extract with gemini] Execution failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()