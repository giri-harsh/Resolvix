"""Twilio WhatsApp Sandbox destination (free, but 24h session window + sandbox
keyword join requirement — §8.2). No-ops with a log warning if unconfigured rather
than raising, so a missing Twilio account never breaks ticket creation.
"""
import logging

from resolvix import settings

logger = logging.getLogger("resolvix.notify.whatsapp")

scheme = "whatsapp"

_client = None
if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
    from twilio.rest import Client

    _client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


async def send(target: str, message: str, ticket: dict) -> None:
    if _client is None:
        logger.warning("whatsapp notify skipped (Twilio not configured) for ticket=%s", ticket.get("id"))
        return
    to = target if target.startswith("whatsapp:") else f"whatsapp:{target}"
    try:
        _client.messages.create(from_=settings.TWILIO_WHATSAPP_NUMBER, to=to, body=message)
    except Exception:
        logger.exception("whatsapp notify failed for ticket=%s", ticket.get("id"))
