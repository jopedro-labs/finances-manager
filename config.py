"""
Centralised configuration via pydantic-settings.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR: Path = Path(__file__).resolve().parent
GEMINI_DIR: Path = ROOT_DIR / ".gemini"
AGENTS_DIR: Path = GEMINI_DIR / "agents"
DATA_DIR: Path = ROOT_DIR / "data"
SNAPSHOTS_DIR: Path = ROOT_DIR / "snapshots"
REPORTS_DIR: Path = ROOT_DIR / "reports"
INFRA_DIR: Path = ROOT_DIR / "infra"
INPUT_DIR: Path = ROOT_DIR / "input"
SCRIPTS_DIR: Path = ROOT_DIR / "scripts"
SECRETS_DIR: Path = ROOT_DIR / "secrets"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-3.8-flash", alias="GEMINI_MODEL")

    gdrive_credentials_file: Path = Field(
        default=SECRETS_DIR / "credentials.json", alias="GDRIVE_CREDENTIALS_FILE"
    )
    gdrive_token_file: Path = Field(default=SECRETS_DIR / "token.json", alias="GDRIVE_TOKEN_FILE")
    gdrive_data_folder_id: str | None = Field(default=None, alias="GDRIVE_DATA_FOLDER_ID")
    gdrive_snapshots_folder_id: str | None = Field(default=None, alias="GDRIVE_SNAPSHOTS_FOLDER_ID")

    @field_validator("gdrive_data_folder_id", "gdrive_snapshots_folder_id")
    @classmethod
    def validate_folder_ids(cls, v: str | None) -> str | None:
        from infra.gdrive.gdrive_helpers import sanitize_gdrive_folder_id

        return sanitize_gdrive_folder_id(v)

    def model_post_init(self, __context: object, /) -> None:
        """
        Ensure essential project directories exist on startup.
        """
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        INPUT_DIR.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached singleton instance of the application settings.
    """
    return Settings()
