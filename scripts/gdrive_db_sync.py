"""Script for synchronizing the local SQLite database (finances.db) with Google Drive storage."""

from __future__ import annotations

import os
from pathlib import Path

from core_lib.gdrive.gdrive_service import GDriveService
from config import get_settings, DATA_DIR
from infra.database.connection import DEFAULT_DB_PATH

settings = get_settings()


def sync_database_to_gdrive() -> None:
    """Uploads or updates the local finances.db database file in Google Drive."""
    folder_id = settings.gdrive_snapshots_folder_id or settings.gdrive_data_folder_id
    db_path = Path(DEFAULT_DB_PATH)

    if not db_path.exists():
        logger.warning(f"[gdrive db sync] Local database not found at {db_path.absolute()}. Nothing to sync.")
        return

    logger.info(f"[gdrive db sync] Connecting to Google Drive (Folder ID: {folder_id})...")
    service = GDriveService(folder_id=folder_id)

    if not service.authenticate():
        logger.error("[gdrive db sync] Authentication with Google Drive failed.")
        return

    logger.info(f"[gdrive db sync] Uploading database '{db_path.name}' to Google Drive...")
    # Using core_lib GDrive service to upload/sync
    success = service.upload_file(db_path)
    if success:
        logger.success("[gdrive db sync] Database successfully synchronized with Google Drive.")
    else:
        logger.error("[gdrive db sync] Failed to upload database to Google Drive.")


if __name__ == "__main__":
    sync_database_to_gdrive()