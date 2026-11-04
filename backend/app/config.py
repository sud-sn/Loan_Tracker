"""Runtime configuration. Everything comes from environment variables (PRD section 13)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

IST = ZoneInfo("Asia/Kolkata")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LT_", env_file=None, extra="ignore")

    env: Literal["production", "development", "test"] = "production"
    database_url: str = "postgresql+psycopg://loantracker:loantracker@localhost:5432/loantracker"
    app_origin: str = "https://localhost"
    data_dir: Path = Path("/data")
    files_dir: Path | None = None

    # Secrets. In production each is read from a file outside the data and backup folders.
    keyring_file: Path = Path("/run/secrets/aadhaar_keyring.json")
    aadhaar_hmac_secret: str = Field(default="", repr=False)
    session_secret: str = Field(default="", repr=False)
    file_link_secret: str = Field(default="", repr=False)

    cookie_secure: bool = True
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    step_up_minutes: int = 5
    file_link_seconds: int = 300

    login_rate_per_minute: int = 10
    lockout_threshold: int = 5

    scanner: Literal["clamd", "builtin"] = "clamd"
    clamd_host: str = "clamav"
    clamd_port: int = 3310

    breached_passwords_file: Path | None = None  # optional SHA-1 list (e.g. HIBP offline)

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = Field(default=None, repr=False)
    alert_email_to: str | None = None
    vapid_private_key: str | None = Field(default=None, repr=False)
    vapid_public_key: str | None = None
    vapid_subject: str = "mailto:owner@localhost"

    backup_status_file: Path = Path("/backups/status.json")
    log_level: str = "INFO"

    @property
    def storage_dir(self) -> Path:
        return self.files_dir or self.data_dir / "files"


@lru_cache
def get_settings() -> Settings:
    return Settings()
