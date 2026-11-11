"""
Authentication module for Google Drive using OAuth2 (installed app flow).

First run: opens a browser for authorization and saves secrets/token.json.
Subsequent runs: loads the saved token with automatic refresh.
"""

from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from config import get_settings

SCOPES: list[str] = ["https://www.googleapis.com/auth/drive.file"]


def get_google_service_credentials(
    credentials_path: str | Path | None = None,
) -> Credentials:
    settings = get_settings()

    creds_path = Path(credentials_path or settings.gdrive_credentials_file)
    token_path = Path(settings.gdrive_token_file)

    creds: Credentials | None = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                raise FileNotFoundError(f"Missing OAuth2 credentials file at {creds_path}")
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)

        assert creds is not None
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())

    return creds
