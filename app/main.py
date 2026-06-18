"""Sunshine application entrypoint.

Run locally with:

    uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from .auth import require_admin
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


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# Respondent survey routes are public; admin routes require Basic Auth.
app.include_router(survey.router)
app.include_router(admin.router, dependencies=[Depends(require_admin)])
