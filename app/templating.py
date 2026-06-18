"""Shared Jinja2 template environment."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from .config import settings

_TEMPLATE_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))
templates.env.globals["base_url"] = settings.base_url
