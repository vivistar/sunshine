"""Email delivery: configurable SMTP with a console/dev fallback.

When ``SMTP_HOST`` is configured, messages are sent over SMTP (STARTTLS or
implicit SSL). Otherwise the app runs in *console mode*: messages are logged
and written to ``dev_outbox/`` as ``.eml`` files so you can develop and test
the full invite flow without real credentials.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from .config import settings

logger = logging.getLogger("sunshine.email")

_OUTBOX = Path("dev_outbox")


def _build_message(to: str, subject: str, html: str, text: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


def send_email(to: str, subject: str, html: str, text: str | None = None) -> bool:
    """Send one email. Returns True if delivered (or written in console mode)."""
    text = text or "This message requires an HTML-capable email client."
    msg = _build_message(to, subject, html, text)

    if not settings.email_enabled:
        return _write_to_outbox(msg, to, subject)

    try:
        if settings.smtp_use_tls:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
                s.starttls(context=ssl.create_default_context())
                if settings.smtp_user:
                    s.login(settings.smtp_user, settings.smtp_password)
                s.send_message(msg)
        else:
            with smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=30,
                context=ssl.create_default_context(),
            ) as s:
                if settings.smtp_user:
                    s.login(settings.smtp_user, settings.smtp_password)
                s.send_message(msg)
        logger.info("Sent email to %s (%s)", to, subject)
        return True
    except Exception:  # noqa: BLE001 — surface delivery failure to caller
        logger.exception("Failed to send email to %s", to)
        return False


def _write_to_outbox(msg: EmailMessage, to: str, subject: str) -> bool:
    _OUTBOX.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    safe_to = to.replace("@", "_at_").replace("/", "_")
    path = _OUTBOX / f"{stamp}_{safe_to}.eml"
    path.write_bytes(bytes(msg))
    logger.info("[console mode] Wrote email for %s to %s", to, path)
    print(f"\n=== [DEV EMAIL] To: {to} | Subject: {subject} ===")
    print(f"    Saved to {path}\n")
    return True


def invitation_email(survey_name: str, link: str) -> tuple[str, str, str]:
    """Build (subject, html, text) for a survey invitation."""
    subject = f"You're invited to take the survey: {survey_name}"
    html = f"""\
<!doctype html>
<html><body style="font-family: -apple-system, Arial, sans-serif; color:#222;">
  <h2 style="color:#e8a13a;">Sunshine Surveys</h2>
  <p>Hello,</p>
  <p>You've been invited to participate in a short choice survey:
     <strong>{survey_name}</strong>.</p>
  <p>It only takes a few minutes. Please click the button below to begin:</p>
  <p>
    <a href="{link}"
       style="background:#e8a13a;color:#fff;padding:12px 20px;border-radius:6px;
              text-decoration:none;display:inline-block;">Start the survey</a>
  </p>
  <p style="color:#666;font-size:13px;">Or paste this link into your browser:<br>
     <a href="{link}">{link}</a></p>
  <p style="color:#999;font-size:12px;">This link is unique to you—please don't
     share it.</p>
</body></html>"""
    text = (
        f"You've been invited to take the survey: {survey_name}\n\n"
        f"Start here: {link}\n\n"
        "This link is unique to you—please don't share it."
    )
    return subject, html, text
