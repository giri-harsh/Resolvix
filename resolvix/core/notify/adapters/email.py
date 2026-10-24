"""SMTP destination — plain stdlib smtplib, no paid API. No-ops if SMTP_* is unset."""
import logging
import smtplib
from email.message import EmailMessage

from resolvix import settings

logger = logging.getLogger("resolvix.notify.email")

scheme = "email"


async def send(target: str, message: str, ticket: dict) -> None:
    if not settings.SMTP_HOST:
        logger.warning("email notify skipped (SMTP not configured) for ticket=%s", ticket.get("id"))
        return
    to = target[len("email:"):] if target.startswith("email:") else target
    msg = EmailMessage()
    msg["Subject"] = f"Resolvix ticket {ticket.get('id')}"
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg.set_content(message)
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_USER:
                server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
    except Exception:
        logger.exception("email notify failed for ticket=%s", ticket.get("id"))
