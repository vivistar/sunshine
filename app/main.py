"""Sunshine application entrypoint.

Run locally with:

    uvicorn app.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .database import init_db
from .routes import admin, survey


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Sunshine — Conjoint Survey Tool", version="0.1.0", lifespan=lifespan
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(survey.router)
app.include_router(admin.router)
