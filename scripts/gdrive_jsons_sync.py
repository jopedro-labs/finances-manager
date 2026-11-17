"""Script for synchronizing local JSON configuration and portfolio files with Google Drive."""

from __future__ import annotations

from pathlib import Path

from core_lib.gdrive.gdrive_service import GDriveService
from config import get_settings, DATA_DIR

settings = get_settings()


def sync_json_files() -> None:
    """Synchronizes all JSON cache and configuration files with Google Drive storage."""
    folder_id = settings.gdrive_data_folder_id
    logger.info(f"[gdrive jsons sync] Starting JSON configuration sync with Google Drive folder: {folder_id}")

    service = GDriveService(folder_id=folder_id)
    if not service.authenticate():
        logger.error("[gdrive jsons sync] Authentication with Google Drive failed.")
        return

    json_files = list(DATA_DIR.glob("*.json"))
    if not json_files:
        logger.info("[gdrive jsons sync] No JSON files found in data directory to sync.")
        return

    for json_file in json_files:
        logger.info(f"[gdrive jsons sync] Uploading configuration file: {json_file.name}")
        service.upload_file(json_file)

    logger.success("[gdrive jsons sync] All JSON configuration files synchronized successfully.")


if __name__ == "__main__":
    sync_json_files()