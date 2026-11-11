"""
Appends a new snapshot to snapshots/snapshots.json and syncs it to Google Drive.

Usage:
    python scripts/snapshot.py <path_to_json_file>

The JSON file must contain a complete snapshot object matching the format in
snapshots/snapshots.json. Pass a file path instead of raw JSON to avoid shell
escaping issues with large or quote-heavy payloads.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from config import SNAPSHOTS_DIR, get_settings
from infra.logger import logger

SNAPSHOTS_FILE: Path = SNAPSHOTS_DIR / "snapshots.json"


def append_snapshot(snapshot: dict[str, Any]) -> None:
    """Appends a new portfolio snapshot to the historical JSON file and persists it safely.

    Reads existing history, ensures data integrity (fallback to list if corrupted),
    prevents duplicate entries for the same date by updating or appending,
    and writes back with pretty formatting.

    Args:
        snapshot: A dictionary containing the structured portfolio snapshot data,
            including date, totals, breakdown, and holdings.

    Returns:
        None
    """
    snapshots: list[dict[str, Any]] = []

    if SNAPSHOTS_FILE.exists():
        try:
            with open(SNAPSHOTS_FILE, encoding="utf-8") as json_file:
                content = json.load(json_file)
                if isinstance(content, list):
                    snapshots = content
                else:
                    logger.warning(
                        "[snapshots] Snapshots.json root is not a list. Resetting history."
                    )
        except json.JSONDecodeError as e:
            logger.warning(f"[snapshots] Snapshots.json is corrupted ({e}). Starting fresh.")

    snapshot_date = snapshot.get("date")

    existing_index = next(
        (i for i, s in enumerate(snapshots) if s.get("date") == snapshot_date), None
    )

    if existing_index is not None:
        snapshots[existing_index] = snapshot
        logger.info(f"[snapshots] Snapshot for {snapshot_date} updated (replaced existing entry).")
    else:
        snapshots.append(snapshot)
        logger.info(f"[snapshots] Snapshot for {snapshot_date} appended.")

    with open(SNAPSHOTS_FILE, "w", encoding="utf-8") as json_file:
        json.dump(snapshots, json_file, ensure_ascii=False, indent=2)

    logger.info(
        f"[snapshots] Total: €{snapshot.get('total_market_value_eur', '?')} "
        f"(P&L: €{snapshot.get('unrealized_pnl_eur', '?')})"
    )


def push_to_gdrive() -> None:
    """Synchronizes the local snapshots file with Google Drive as a backup.

    Retrieves the dedicated Google Drive snapshot folder ID from configuration,
    initializes the GDrive service, and attempts to back up the snapshots JSON file.
    Fails gracefully with a warning log if network or sync errors occur.

    Returns:
        None
    """
    try:
        from infra.gdrive import GDriveService

        settings = get_settings()
        folder_id = settings.gdrive_snapshots_folder_id

        drive = GDriveService(folder_id=folder_id)
        success = drive.backup_file(SNAPSHOTS_FILE)

        if not success:
            logger.warning("[snapshots] Could not sync with Google Drive.")

    except Exception as error:
        logger.error(f"[snapshots] Error syncing with Google Drive: {error}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.info("[snapshots] Usage: python scripts/snapshot.py <path_to_json_file>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        logger.error(f"[snapshots] File not found — {input_path}")
        sys.exit(1)

    try:
        with open(input_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"[snapshots] Invalid JSON — {e}")
        sys.exit(1)

    append_snapshot(data)
    push_to_gdrive()

    # Remove the temporary input file after successful processing
    if input_path.name == ".temp_snapshot.json":
        input_path.unlink(missing_ok=True)
