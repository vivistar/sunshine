"""Lightweight audit logging for security-relevant admin actions.

Events (admin logins and survey creation) are written to a dedicated
``sunshine.audit`` logger that owns its own stderr handler, so the audit trail
surfaces regardless of how the host configures application logging. Failed
logins are logged at WARNING; routine events at INFO.
"""

from __future__ import annotations

import logging

from fastapi import Request

logger = logging.getLogger("sunshine.audit")
if not logger.handlers:  # configure once; guard against duplicate handlers
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [audit] %(message)s")
    )
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def client_ip(request: Request) -> str:
    """Best-effort client IP, honoring a proxy's ``X-Forwarded-For`` first hop.

    Behind a reverse proxy (e.g. Render) ``request.client`` is the proxy, so the
    real client appears in ``X-Forwarded-For``. We take the first hop and fall
    back to the direct peer when the header is absent.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    return request.client.host if request.client else "unknown"


def record(
    event: str, request: Request, *, level: int = logging.INFO, **fields: object
) -> None:
    """Emit one audit line: ``event key=value ... ip=<addr>``."""
    parts = [f"{key}={value!r}" for key, value in fields.items()]
    parts.append(f"ip={client_ip(request)}")
    logger.log(level, "%s %s", event, " ".join(parts))
