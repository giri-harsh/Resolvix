"""Vobiz WhatsApp Business API destination (pivot v3 §7 — additive, non-core,
same Destination protocol as whatsapp.py/webhook.py). Confirmed live against
Vobiz's own docs: POST https://api.vobiz.ai/api/v1/messaging/messages, auth via
X-Auth-ID/X-Auth-Token headers, requires a provisioned WhatsApp Business Account
(waba_id) and channel_id — a real account only the user can set up, not
something buildable from here. No-ops with a log warning if unconfigured, same
pattern as every other adapter, so a missing account never breaks ticket
creation. UNTESTED LIVE — needs real VOBIZ_* credentials to verify end to end.
"""
import logging

import httpx

from resolvix import settings

logger = logging.getLogger("resolvix.notify.vobiz")

scheme = "vobiz"

_API_URL = "https://api.vobiz.ai/api/v1/messaging/messages"


async def send(target: str, message: str, ticket: dict) -> None:
    if not (settings.VOBIZ_AUTH_ID and settings.VOBIZ_AUTH_TOKEN and settings.VOBIZ_CHANNEL_ID and settings.VOBIZ_WABA_ID):
        logger.warning("vobiz notify skipped (not configured) for ticket=%s", ticket.get("id"))
        return
    to = target[len("vobiz:"):] if target.startswith("vobiz:") else target
    body = {
        "channel_id": settings.VOBIZ_CHANNEL_ID,
        "waba_id": settings.VOBIZ_WABA_ID,
        "to": to,
        "type": "text",
        "text": {"body": message},
    }
    headers = {
        "X-Auth-ID": settings.VOBIZ_AUTH_ID,
        "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(_API_URL, json=body, headers=headers)
            resp.raise_for_status()
    except Exception:
        logger.exception("vobiz notify failed for ticket=%s", ticket.get("id"))
