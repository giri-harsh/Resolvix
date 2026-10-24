"""Generic webhook destination (Discord/Slack incoming webhook, unlimited free tier).
Preferred over WhatsApp when a queue's escalation.yaml target starts with `webhook:`."""
import logging

import httpx

logger = logging.getLogger("resolvix.notify.webhook")

scheme = "webhook"


async def send(target: str, message: str, ticket: dict) -> None:
    url = target[len("webhook:"):] if target.startswith("webhook:") else target
    if not (url.startswith("http://") or url.startswith("https://")):
        # Placeholder destination (e.g. "webhook:REPLACE_WITH_REAL_URL") — skip
        # the network call entirely rather than let httpx raise UnsupportedProtocol.
        # Already caught safely either way; this just avoids the noisy traceback.
        logger.warning("webhook notify skipped (not a real URL: %r) for ticket=%s", url, ticket.get("id"))
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url, json={"content": message})
    except Exception:
        logger.exception("webhook notify failed for ticket=%s", ticket.get("id"))
