from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from core_lib.gdrive.gdrive_service import GDriveService


@pytest.fixture
def service() -> GDriveService:
    return GDriveService(folder_id="test-folder")


def test_service_returns_falsy_when_get_service_is_none(
    service: GDriveService, tmp_path: Path
) -> None:
    """Test null service guardrails across all methods."""
    with patch.object(service, "_get_service", return_value=None):
        assert service.verify_folder_access() is False
        assert service.file_exists("test.txt") is False
        assert service.list_files() == []
        dummy_file: Path = tmp_path / "dummy.txt"
        dummy_file.write_text("content", encoding="utf-8")
        assert service.upload_file(dummy_file) is None
        assert service.download_file("test.txt", tmp_path / "out.txt") is False
        assert service.backup_file(dummy_file) is False


def test_service_handle_api_exceptions(service: GDriveService, tmp_path: Path) -> None:
    """Test exception handling in methods with try/except blocks."""
    mock_service: MagicMock = MagicMock()
    mock_service.files.side_effect = RuntimeError("API Error")

    with patch.object(service, "_get_service", return_value=mock_service):
        assert service.verify_folder_access() is False
        assert service.file_exists("test.txt") is False
        assert service.list_files() == []
        f: Path = tmp_path / "test.txt"
        f.write_text("dummy", encoding="utf-8")
        assert service.upload_file(f) is None


def test_init_validation(tmp_path: Path) -> None:
    """Test credentials file existence check during instantiation."""
    with pytest.raises(FileNotFoundError):
        GDriveService(credentials_path=tmp_path / "non_existent_file.json")


def test_verify_folder_access_no_target_folder() -> None:
    """Test folder verification when no target folder ID is defined."""
    svc: GDriveService = GDriveService(folder_id=None)
    with patch.object(svc, "_get_service", return_value=MagicMock()):
        assert svc.verify_folder_access() is False


def test_sync_files_invalid_direction(service: GDriveService) -> None:
    """Test ValueError handling when an invalid sync direction is provided."""
    results: dict[str, bool] = service.sync_files(["test.txt"], direction="invalid")
    assert results == {"test.txt": False}


def test_download_file_not_found(service: GDriveService, tmp_path: Path) -> None:
    """Test branch where remote file is not found on Google Drive."""
    mock_service: MagicMock = MagicMock()
    mock_service.files().list().execute.return_value = {"files": []}
    with patch.object(service, "_get_service", return_value=mock_service):
        assert service.download_file("missing.txt", tmp_path / "out.txt") is False


def test_download_file_api_exception(service: GDriveService, tmp_path: Path) -> None:
    """Test media download stream failure handling."""
    mock_service: MagicMock = MagicMock()
    mock_service.files().list().execute.return_value = {"files": [{"id": "file-123"}]}
    mock_service.files().get_media.side_effect = RuntimeError("Stream broken")
    with patch.object(service, "_get_service", return_value=mock_service):
        assert service.download_file("test.txt", tmp_path / "out.txt") is False


def test_upload_file_non_existent_local(service: GDriveService, tmp_path: Path) -> None:
    """Test upload attempt of a non-existent local file."""
    assert service.upload_file(tmp_path / "does_not_exist.bin") is None
