import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from core_lib.gdrive.gdrive_service import GDriveService

@pytest.fixture
def service():
    return GDriveService(folder_id="test-folder")

def test_service_returns_falsy_when_get_service_is_none(service, tmp_path):
    """Testa os guardrails de serviço nulo em todos os métodos existentes."""
    with patch.object(service, "_get_service", return_value=None):
        assert service.verify_folder_access() is False
        assert service.file_exists("test.txt") is False
        assert service.list_files() == []
        dummy_file = tmp_path / "dummy.txt"
        dummy_file.write_text("content")
        assert service.upload_file(dummy_file) is None
        assert service.download_file("test.txt", tmp_path / "out.txt") is False
        assert service.backup_file(dummy_file) is False

def test_service_handle_api_exceptions(service, tmp_path):
    """Testa o tratamento de exceções em métodos com blocos try/except."""
    mock_service = MagicMock()
    mock_service.files.side_effect = RuntimeError("API Error")
    
    with patch.object(service, "_get_service", return_value=mock_service):
        assert service.verify_folder_access() is False
        assert service.file_exists("test.txt") is False
        assert service.list_files() == []
        f = tmp_path / "test.txt"
        f.write_text("dummy")
        assert service.upload_file(f) is None

def test_init_validation(tmp_path):
    """Testa a validação do ficheiro de credenciais no __init__."""
    with pytest.raises(FileNotFoundError):
        GDriveService(credentials_path=tmp_path / "non_existent_file.json")

def test_verify_folder_access_no_target_folder():
    """Testa o caso onde não há folder_id (nem na instância, nem passado como argumento)."""
    svc = GDriveService(folder_id=None)
    with patch.object(svc, "_get_service", return_value=MagicMock()):
        assert svc.verify_folder_access() is False

def test_sync_files_invalid_direction(service):
    """Testa a exceção ValueError no sync_files."""
    results = service.sync_files(["test.txt"], direction="invalid")
    assert results == {"test.txt": False}

def test_download_file_not_found(service, tmp_path):
    """Testa o ramo onde o ficheiro a transferir não é encontrado no Google Drive."""
    mock_service = MagicMock()
    mock_service.files().list().execute.return_value = {"files": []}
    with patch.object(service, "_get_service", return_value=mock_service):
        assert service.download_file("missing.txt", tmp_path / "out.txt") is False

def test_download_file_api_exception(service, tmp_path):
    """Testa falha de download no get_media ou streaming."""
    mock_service = MagicMock()
    mock_service.files().list().execute.return_value = {"files": [{"id": "file-123"}]}
    mock_service.files().get_media.side_effect = RuntimeError("Stream broken")
    with patch.object(service, "_get_service", return_value=mock_service):
        assert service.download_file("test.txt", tmp_path / "out.txt") is False

def test_upload_file_non_existent_local(service, tmp_path):
    """Testa upload de ficheiro local inexistente."""
    assert service.upload_file(tmp_path / "does_not_exist.bin") is None
