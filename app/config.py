"""Application configuration, loaded from environment / .env file."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # General
    base_url: str = "http://localhost:8000"
    database_url: str = "sqlite:///./sunshine.db"

    # Email / SMTP. When smtp_host is empty the app runs in "console" mode:
    # invitations are logged and written to dev_outbox/ instead of being sent.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Sunshine Surveys <no-reply@sunshine.local>"
    smtp_use_tls: bool = True

    @property
    def email_enabled(self) -> bool:
        """True when real SMTP delivery is configured."""
        return bool(self.smtp_host)


settings = Settings()
