"""Sunshine application entrypoint.

Run locally with:

    uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from . import auth
from .auth import NotAuthenticated, require_admin, session_secret
from .config import settings
from .database import init_db
from .routes import admin, survey

logger = logging.getLogger("sunshine")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if not settings.auth_enabled:
        logger.warning(
            "Admin auth is DISABLED (ADMIN_PASSWORD is empty). The researcher "
            "UI is open. Set ADMIN_PASSWORD to require login."
        )
    yield


app = FastAPI(
    title="Sunshine — Survey & Conjoint Tool", version="0.2.0", lifespan=lifespan
)

# Signed session cookie backs the admin login. The secret is derived from the
# admin password by default (see auth.session_secret).
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret(),
    session_cookie="sunshine_session",
    max_age=60 * 60 * 8,  # 8 hours
    same_site="lax",
)


@app.exception_handler(NotAuthenticated)
async def _login_redirect(request: Request, exc: NotAuthenticated) -> RedirectResponse:
    """Send signed-out visitors to the login page, preserving where they were headed."""
    return RedirectResponse(url=f"/login?next={request.url.path}", status_code=303)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# Login/logout and respondent survey routes are public; admin routes require login.
app.include_router(auth.router)
app.include_router(survey.router)
app.include_router(admin.router, dependencies=[Depends(require_admin)])
