import os

from core_lib.gdrive.gdrive_service import GDriveService
from core_lib.logger.logger import setup_logger

logger = setup_logger("finances-manager-gdrive-sync")


def sync_from_drive() -> None:
    folder_id = os.getenv("GDRIVE_DATA_FOLDER_ID")
    service = GDriveService(folder_id=folder_id)

    if not service.authenticate():
        logger.error("Failed to authenticate with Google Drive.")
        return

    logger.info("Successfully connected to Google Drive. Ready for synchronization.")


if __name__ == "__main__":
    sync_from_drive()
