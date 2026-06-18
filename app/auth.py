"""Admin authentication via HTTP Basic Auth.

Enforced only when ``ADMIN_PASSWORD`` is configured. When it is empty the
dependency is a no-op so the admin UI is reachable during local development.
Respondent survey routes never use this dependency and stay public.
"""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .config import settings

_basic = HTTPBasic(auto_error=False)


def require_admin(
    credentials: HTTPBasicCredentials | None = Depends(_basic),
) -> None:
    if not settings.auth_enabled:
        return  # auth disabled (no password configured)

    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Basic"},
    )
    if credentials is None:
        raise unauthorized

    # Constant-time comparison to avoid leaking length/contents via timing.
    user_ok = secrets.compare_digest(credentials.username, settings.admin_user)
    pass_ok = secrets.compare_digest(credentials.password, settings.admin_password)
    if not (user_ok and pass_ok):
        raise unauthorized
