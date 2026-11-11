"""
Service wrapper for Google Drive operations.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.http import (
    MediaFileUpload,
    MediaIoBaseDownload,
)

from config import get_settings
from infra.gdrive.gdrive_auth import get_google_service_credentials
from infra.logger import logger


class GDriveService:
    """
    Wrapper for Google Drive operations using OAuth2 user credentials.
    """

    def __init__(
        self,
        credentials_path: str | Path | None = None,
        folder_id: str | None = None,
    ) -> None:
        """Initializes the Google Drive service wrapper.

        Args:
            credentials_path: Optional path to the OAuth2 credentials JSON file (credentials.json).
            folder_id: Optional target Google Drive folder ID for operations.
        """
        if credentials_path and not Path(credentials_path).exists():
            raise FileNotFoundError(f"[GDrive] Missing Google credentials file: {credentials_path}")
        self.credentials_path = credentials_path
        self.folder_id: str | None = folder_id or get_settings().gdrive_data_folder_id
        self._service: Any | None = None

    def _get_service(self) -> Any | None:
        """Lazily initializes and returns the Google Drive API client service.

        Returns:
            The authenticated Google API resource object for Drive v3, or None if initialization fails.
        """
        if self._service is None:
            try:
                creds = get_google_service_credentials(
                    credentials_path=self.credentials_path,
                )
                if not creds:
                    logger.warning("[GDrive] No valid credentials available.")
                    return None
                self._service = build("drive", "v3", credentials=creds)
            except Exception as e:
                logger.error(f"[GDrive] Failed to initialise service: {e}")
                return None
        return self._service

    def verify_folder_access(self, folder_id: str | None = None) -> bool:
        """Verifies remotely if a Google Drive folder exists and is accessible.

        Args:
            folder_id: The Google Drive folder ID to check. Defaults to instance folder_id.

        Returns:
            True if the folder exists, is accessible, and is of type folder.
        """
        service = self._get_service()
        if not service:
            return False

        target_folder = folder_id or self.folder_id
        if not target_folder:
            return False

        try:
            file_metadata: dict[str, Any] = (
                service.files().get(fileId=target_folder, fields="id, mimeType").execute()
            )
            return file_metadata.get("mimeType") == "application/vnd.google-apps.folder"
        except Exception as e:
            logger.error(f"[GDrive] Error verifying folder '{target_folder}': {e}")
            return False

    def file_exists(self, file_name: str, folder_id: str | None = None) -> bool:
        """Checks whether a file with the given name exists in Google Drive.

        Args:
            file_name: The name of the file to search for.
            folder_id: Optional folder ID to restrict the search. Defaults to instance folder_id.

        Returns:
            True if the file exists and is not in trash, False otherwise.
        """
        service = self._get_service()
        if not service:
            return False
        target_folder = folder_id or self.folder_id
        safe_name = file_name.replace("'", "\\'")
        query = f"name = '{safe_name}' and trashed = false"
        if target_folder:
            query += f" and '{target_folder}' in parents"
        try:
            response: dict[str, list[dict[str, str]]] = (
                service.files().list(q=query, fields="files(id)").execute()
            )
            return len(response.get("files", [])) > 0
        except Exception as e:
            logger.error(f"[GDrive] Error checking file '{file_name}': {e}")
            return False

    def list_files(self, folder_id: str | None = None, limit: int = 100) -> list[dict[str, str]]:
        """Lists files located inside a specific Google Drive folder.

        Args:
            folder_id: Optional folder ID to list files from. Defaults to instance folder_id.
            limit: Maximum number of files to return (default is 100).

        Returns:
            A list of dictionaries containing file identifiers and names.
        """
        service = self._get_service()
        if not service:
            return []
        target_folder = folder_id or self.folder_id
        query = "trashed = false"
        if target_folder:
            query = f"'{target_folder}' in parents and trashed = false"
        try:
            response: dict[str, list[dict[str, str]]] = (
                service.files().list(q=query, pageSize=limit, fields="files(id, name)").execute()
            )
            return response.get("files", [])
        except Exception as e:
            logger.error(f"[GDrive] Error listing files: {e}")
            return []

    def upload_file(
        self,
        file_path: str | Path,
        folder_id: str | None = None,
        overwrite: bool = False,
        mime_type: str = "application/octet-stream",
    ) -> str | None:
        """Uploads a local file to Google Drive.

        Args:
            file_path: Path to the local file to upload.
            folder_id: Optional destination folder ID. Defaults to instance folder_id.
            overwrite: If True, updates an existing file with the same name instead of creating a duplicate.
            mime_type: The MIME type of the file being uploaded.

        Returns:
            The Google Drive file ID if successful, or None otherwise.
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"[GDrive] File not found: '{path}'.")
            return None
        service = self._get_service()
        if not service:
            return None
        target_folder = folder_id or self.folder_id
        media = MediaFileUpload(str(path), mimetype=mime_type, resumable=True)
        try:
            if overwrite:
                safe_name = path.name.replace("'", "\\'")
                query = f"name = '{safe_name}' and trashed = false"
                if target_folder:
                    query += f" and '{target_folder}' in parents"
                existing_resp: dict[str, list[dict[str, str]]] = (
                    service.files().list(q=query, fields="files(id)").execute()
                )
                existing_files = existing_resp.get("files", [])
                if existing_files:
                    file_id = existing_files[0]["id"]
                    service.files().update(fileId=file_id, media_body=media).execute()
                    logger.info(f"[GDrive] '{path.name}' updated.")
                    return file_id
            file_metadata = {
                "name": path.name,
                "parents": [target_folder] if target_folder else [],
            }
            created_file: dict[str, str] = (
                service.files().create(body=file_metadata, media_body=media, fields="id").execute()
            )
            logger.success(f"[GDrive] '{path.name}' uploaded successfully.")
            return created_file.get("id")
        except Exception as e:
            logger.error(f"[GDrive] Upload failed for '{path.name}': {e}")
            return None

    def download_file(
        self,
        file_name: str,
        destination_path: str | Path,
        folder_id: str | None = None,
    ) -> bool:
        """Downloads a file from Google Drive to a local destination path.

        Args:
            file_name: Name of the file on Google Drive to download.
            destination_path: Local file path where the content will be saved.
            folder_id: Optional folder ID where the file is located. Defaults to instance folder_id.

        Returns:
            True if the download was successful, False otherwise.
        """
        dest = Path(destination_path)
        service = self._get_service()
        if not service:
            return False
        target_folder = folder_id or self.folder_id
        safe_name = file_name.replace("'", "\\'")
        query = f"name = '{safe_name}' and trashed = false"
        if target_folder:
            query += f" and '{target_folder}' in parents"
        try:
            response: dict[str, list[dict[str, str]]] = (
                service.files().list(q=query, fields="files(id)").execute()
            )
            files = response.get("files", [])
            if not files:
                logger.warning(f"[GDrive] '{file_name}' not found in folder '{target_folder}'.")
                return False
            file_id = files[0]["id"]
            request = service.files().get_media(fileId=file_id)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with io.BytesIO() as fh:
                downloader = MediaIoBaseDownload(fh, request)
                while not downloader.next_chunk()[1]:
                    pass
                dest.write_bytes(fh.getvalue())
            logger.info(f"[GDrive] '{file_name}' downloaded to '{dest}'.")
            return True
        except Exception as e:
            logger.error(f"[GDrive] Download failed for '{file_name}': {e}")
            return False

    def backup_file(self, file_path: str | Path, folder_id: str | None = None) -> bool:
        """Backs up a local file by overwriting its remote counterpart or creating it if missing.

        Args:
            file_path: Path to the local file to back up.
            folder_id: Optional destination folder ID. Defaults to instance folder_id.

        Returns:
            True if the backup upload succeeded, False otherwise.
        """
        return self.upload_file(file_path, folder_id=folder_id, overwrite=True) is not None

    def sync_files(
        self, file_paths: Sequence[str | Path], direction: str = "pull"
    ) -> dict[str, bool]:
        """Synchronizes a sequence of local files with Google Drive (pull or push).

        Args:
            file_paths: A sequence of local file paths to synchronize.
            direction: Synchronization direction, either 'pull' (download) or 'push' (upload).

        Returns:
            A dictionary mapping each filename to a boolean status indicating success.
        """
        results: dict[str, bool] = {}
        for file_path in file_paths:
            path = Path(file_path)
            try:
                if direction == "pull":
                    results[path.name] = self.download_file(path.name, path)
                elif direction == "push":
                    results[path.name] = self.upload_file(path, overwrite=True) is not None
                else:
                    raise ValueError(f"[GDrive] Invalid direction: {direction}")
            except Exception as e:
                logger.error(f"[GDrive] Sync error for {path.name}: {e}")
                results[path.name] = False
        return results
