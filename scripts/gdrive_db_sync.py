"""Script for synchronizing the local SQLite database (finances.db) with Google Drive storage."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure root directory is in pythonpath
_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

from core_lib.gdrive.gdrive_service import GDriveService
from core_lib.logger import logger

from config import get_settings
from infra.database.connection import DEFAULT_DB_PATH

settings = get_settings()


def sync_database_to_gdrive() -> None:
    """Uploads or updates the local finances.db database file in Google Drive."""
    folder_id = settings.gdrive_snapshots_folder_id or settings.gdrive_data_folder_id
    db_path = Path(DEFAULT_DB_PATH)

    if not db_path.exists():
        logger.warning(
            f"[gdrive db sync] Local database not found at {db_path.absolute()}. Nothing to sync."
        )
        return

    logger.info(f"[gdrive db sync] Connecting to Google Drive (Folder ID: {folder_id})...")
    service = GDriveService(
        credentials_path=settings.gdrive_credentials_file,
        token_path=settings.gdrive_token_file,
        folder_id=folder_id,
    )

    logger.info(f"[gdrive db sync] Uploading/updating database '{db_path.name}' on Google Drive...")

    success = service.upload_file(db_path, overwrite=True)

    if success:
        logger.success("[gdrive db sync] Database successfully synchronized with Google Drive.")
    else:
        logger.error("[gdrive db sync] Failed to upload database to Google Drive.")


def pull_database_from_gdrive() -> None:
    """Downloads the latest finances.db from Google Drive to the local path."""
    folder_id = settings.gdrive_snapshots_folder_id or settings.gdrive_data_folder_id
    db_path = Path(DEFAULT_DB_PATH)

    logger.info(f"[gdrive db sync] Connecting to Google Drive (Folder ID: {folder_id})...")
    service = GDriveService(
        credentials_path=settings.gdrive_credentials_file,
        token_path=settings.gdrive_token_file,
        folder_id=folder_id,
    )

    logger.info(f"[gdrive db sync] Downloading '{db_path.name}' from Google Drive...")
    success = service.download_file(file_name=db_path.name, destination_path=db_path)
    if success:
        logger.success(f"[gdrive db sync] Database downloaded to '{db_path}'.")
    else:
        logger.warning(
            "[gdrive db sync] Database not found on Google Drive — starting fresh from local state."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sync finances.db with Google Drive (upload by default)."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--pull",
        action="store_true",
        help="Download the database from Google Drive instead of uploading.",
    )
    group.add_argument(
        "--push",
        action="store_true",
        help="Upload the local database to Google Drive (default behaviour).",
    )
    args = parser.parse_args()

    if args.pull:
        pull_database_from_gdrive()
    else:
        sync_database_to_gdrive()
