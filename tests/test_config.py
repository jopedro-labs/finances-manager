from __future__ import annotations

import pytest

from config import Settings


def test_default_settings_values() -> None:
    """Verify default configurations match project specifications."""
    settings: Settings = Settings()
    assert settings.gemini_model == "gemini-3.8-flash"
    assert settings.monthly_contribution == 300.0
    assert settings.inflation_rate == 0.02
    assert settings.finance_db_file.name == "finances.db"
    assert settings.max_country_allocation_pct == 60.0
    assert settings.max_tech_allocation_pct == 50.0


def test_settings_custom_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify environment variable overrides for settings."""
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("MONTHLY_CONTRIBUTION", "500.0")
    monkeypatch.setenv("INFLATION_RATE", "0.025")

    settings: Settings = Settings()
    assert settings.gemini_model == "gemini-2.5-flash"
    assert settings.monthly_contribution == 500.0
    assert settings.inflation_rate == 0.025


def test_folder_id_sanitization(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Google Drive folder ID sanitization validator."""
    monkeypatch.setenv("GDRIVE_DATA_FOLDER_ID", "  test-folder-123  ")
    settings: Settings = Settings()
    assert settings.gdrive_data_folder_id == "test-folder-123"

    monkeypatch.setenv("GDRIVE_DATA_FOLDER_ID", "invalid'id")
    with pytest.raises(ValueError):
        Settings()


def test_directory_creation_on_init() -> None:
    """Verify post init directory creation guards."""
    settings: Settings = Settings()
    assert settings.finance_db_file.parent.exists()
