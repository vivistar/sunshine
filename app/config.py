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

    # Admin (researcher) login. Enforcement is enabled only when admin_password
    # is non-empty; otherwise the admin UI is open (handy for local
    # development). Respondent survey links are always public.
    admin_user: str = "admin"
    admin_password: str = ""

    # Secret used to sign the admin session cookie. Optional: when empty a
    # stable secret is derived from admin_password (see auth.session_secret).
    secret_key: str = ""

    @property
    def email_enabled(self) -> bool:
        """True when real SMTP delivery is configured."""
        return bool(self.smtp_host)

    @property
    def auth_enabled(self) -> bool:
        """True when admin login should be enforced."""
        return bool(self.admin_password)


settings = Settings()
