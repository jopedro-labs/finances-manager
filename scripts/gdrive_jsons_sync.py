"""Script for synchronizing local JSON configuration and portfolio files with Google Drive."""

from __future__ import annotations

import argparse

from core_lib.gdrive.gdrive_service import GDriveService
from core_lib.logger import logger

from config import DATA_DIR, get_settings

settings = get_settings()


def _get_service() -> GDriveService:
    """Instantiates a GDriveService using centralized configuration."""
    folder_id = settings.gdrive_data_folder_id
    return GDriveService(
        credentials_path=settings.gdrive_credentials_file,
        token_path=settings.gdrive_token_file,
        folder_id=folder_id,
    )


def push_json_files() -> None:
    """Uploads local JSON cache and configuration files to Google Drive."""
    folder_id = settings.gdrive_data_folder_id
    logger.info(
        f"[gdrive jsons sync] Starting JSON configuration upload to Google Drive folder: {folder_id}"
    )

    service = _get_service()
    json_files = list(DATA_DIR.glob("*.json"))
    if not json_files:
        logger.info("[gdrive jsons sync] No JSON files found in data directory to push.")
        return

    for json_file in json_files:
        logger.info(f"[gdrive jsons sync] Uploading configuration file: {json_file.name}")
        service.upload_file(json_file, overwrite=True)

    logger.success("[gdrive jsons sync] All JSON configuration files uploaded successfully.")


def pull_json_files() -> None:
    """Downloads JSON configuration files from Google Drive to local data directory."""
    folder_id = settings.gdrive_data_folder_id
    logger.info(
        f"[gdrive jsons sync] Starting JSON configuration pull from Google Drive folder: {folder_id}"
    )

    service = _get_service()
    remote_files = service.list_files(folder_id=folder_id)

    json_remotes = [f for f in remote_files if f.get("name", "").endswith(".json")]
    if not json_remotes:
        logger.info("[gdrive jsons sync] No remote JSON files found on Google Drive to download.")
        return

    for file_meta in json_remotes:
        name = file_meta["name"]
        destination_path = DATA_DIR / name
        logger.info(f"[gdrive jsons sync] Downloading remote JSON configuration: {name}")
        service.download_file(
            file_name=name, destination_path=destination_path, folder_id=folder_id
        )

    logger.success("[gdrive jsons sync] All JSON configuration files downloaded successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sync JSON configuration files with Google Drive (upload by default)."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--pull",
        action="store_true",
        help="Download JSON configuration files from Google Drive.",
    )
    group.add_argument(
        "--push",
        action="store_true",
        help="Upload local JSON configuration files to Google Drive (default behavior).",
    )
    args = parser.parse_args()

    if args.pull:
        pull_json_files()
    else:
        push_json_files()
