"""Admin authentication via a browser login form + signed session cookie.

Enforced only when ``ADMIN_PASSWORD`` is configured. When it is empty the
``require_admin`` dependency is a no-op so the admin UI is reachable during
local development. Respondent survey routes never use this dependency and stay
public.
"""

from __future__ import annotations

import hashlib
import logging
import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from . import audit
from .config import settings
from .templating import templates


class NotAuthenticated(Exception):
    """Raised by ``require_admin`` when a signed-in admin session is missing.

    A handler registered in ``app.main`` turns this into a redirect to the
    login page.
    """


def session_secret() -> str:
    """Stable secret for signing the session cookie.

    Prefers an explicit ``SECRET_KEY``; otherwise derives a stable value from
    the admin password so sessions survive restarts without extra config.
    Falls back to a fixed development value when auth is disabled (the cookie
    is meaningless then anyway).
    """
    if settings.secret_key:
        return settings.secret_key
    if settings.admin_password:
        return hashlib.sha256(
            f"sunshine-session:{settings.admin_password}".encode()
        ).hexdigest()
    return "sunshine-dev-insecure-secret"


def credentials_valid(username: str, password: str) -> bool:
    """Constant-time check of submitted credentials against the configured admin."""
    user_ok = secrets.compare_digest(username, settings.admin_user)
    pass_ok = secrets.compare_digest(password, settings.admin_password)
    return bool(settings.admin_password) and user_ok and pass_ok


def require_admin(request: Request) -> None:
    """Guard admin routes; raises ``NotAuthenticated`` when signed out."""
    if not settings.auth_enabled:
        return  # auth disabled (no password configured)
    if request.session.get("admin"):
        return
    raise NotAuthenticated()


def _safe_next(target: str | None) -> str:
    """Only allow same-site relative redirects to avoid open-redirect abuse."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return "/"
    return target


router = APIRouter()


@router.get("/login")
def login_form(request: Request, next: str = "/"):
    nxt = _safe_next(next)
    # Nothing to log in to when auth is off, or already signed in.
    if not settings.auth_enabled or request.session.get("admin"):
        return RedirectResponse(nxt, status_code=303)
    return templates.TemplateResponse(request, "login.html", {"next": nxt})


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    next: str = Form("/"),
):
    nxt = _safe_next(next)
    if credentials_valid(username, password):
        request.session["admin"] = True
        audit.record("admin_login_success", request, user=username)
        return RedirectResponse(nxt, status_code=303)
    audit.record(
        "admin_login_failed", request, user=username, level=logging.WARNING
    )
    return templates.TemplateResponse(
        request,
        "login.html",
        {"next": nxt, "error": "Incorrect username or password."},
        status_code=401,
    )


@router.get("/logout")
def logout(request: Request):
    if request.session.get("admin"):
        audit.record("admin_logout", request)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
