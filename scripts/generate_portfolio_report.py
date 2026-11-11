"""
Analysis and Reporting script using Google Gemini API (google-genai SDK).
Reads prompt instructions from analyst.md/reporter.md and data/rules.md,
evaluates portfolio health, and generates reports saved to reports/.
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

from google import genai
from google.genai import types
from google.genai.errors import APIError

from config import AGENTS_DIR, DATA_DIR, REPORTS_DIR, SNAPSHOTS_DIR, get_settings
from infra.logger import logger
from infra.utils.file_utils import load_file_content

SNAPSHOTS_FILE: Path = SNAPSHOTS_DIR / "snapshots.json"
RULES_FILE: Path = DATA_DIR / "rules.md"
ANALYST_FILE: Path = AGENTS_DIR / "analyst.md"
REPORTER_FILE: Path = AGENTS_DIR / "reporter.md"


def main() -> None:
    """Execute the portfolio analysis and reporting pipeline.

    Reads governance rules, historical snapshots, and agent instructions,
    invokes the Gemini API to analyze portfolio health, and outputs
    the results in either Markdown (terminal) or HTML format (index.html).
    """
    mode = sys.argv[1] if len(sys.argv) > 1 else "md"

    if mode not in ("md", "html"):
        logger.error(f"[generate report] Invalid mode '{mode}'. Use 'md' or 'html'.")
        sys.exit(1)

    settings = get_settings()

    api_key = settings.gemini_api_key
    if not api_key:
        logger.error(
            "[generate report] GEMINI_API_KEY environment variable is not set in configuration or .env."
        )
        sys.exit(1)

    model_name = settings.gemini_model

    analyst_instructions = load_file_content(ANALYST_FILE)
    reporter_instructions = load_file_content(REPORTER_FILE)
    rules_data = load_file_content(RULES_FILE)
    snapshots_raw = load_file_content(SNAPSHOTS_FILE)

    if not snapshots_raw:
        logger.error(f"[generate report] '{SNAPSHOTS_FILE}' not found or empty.")
        sys.exit(1)

    # Validate JSON integrity and structure before calling the API
    try:
        snapshots_data = json.loads(snapshots_raw)
    except json.JSONDecodeError as e:
        logger.error("[generate report] snapshots.json contains invalid JSON", exception=e)
        sys.exit(1)

    if not isinstance(snapshots_data, list):
        logger.error(
            f"[generate report] Invalid snapshots structure: expected a list, got {type(snapshots_data).__name__}."
        )
        sys.exit(1)

    if len(snapshots_data) == 0:
        logger.error(
            "[generate report] snapshots.json list is empty. At least one historical snapshot is required for analysis."
        )
        sys.exit(1)

    if not analyst_instructions:
        logger.warning(
            f"[generate report] '{ANALYST_FILE}' not found — analyst instructions will be empty."
        )
    if not reporter_instructions:
        logger.warning(
            f"[generate report] '{REPORTER_FILE}' not found — reporter instructions will be empty."
        )

    client = genai.Client(api_key=api_key)

    system_instruction = f"""
    {analyst_instructions}

    ---
    {reporter_instructions}
    """

    prompt = f"""
    Here are the governance and calculation rules:
    {rules_data}

    Here is the historical snapshots data:
    {json.dumps(snapshots_data, indent=2)}

    Task: Analyze the portfolio and generate the complete report in {mode.upper()} format following the structure defined in your instructions.
    """

    logger.info(f"[generate report] Generating report via Gemini using model: {model_name}...")

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction, temperature=0.1
            ),
        )
    except APIError as e:
        logger.error("[generate report] API Error during Gemini generation", exception=e)
        sys.exit(1)
    except Exception as e:
        logger.error("[generate report] Unexpected error", exception=e)
        sys.exit(1)

    report_content = response.text
    if not report_content:
        logger.error("[generate report] Gemini returned an empty response.")
        sys.exit(1)

    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    ext = "html" if mode == "html" else "md"
    output_path = REPORTS_DIR / f"{date_str}.{ext}"
    output_path.write_text(report_content, encoding="utf-8")
    logger.success(f"[generate report] Report saved to '{output_path}'.")


if __name__ == "__main__":
    main()
