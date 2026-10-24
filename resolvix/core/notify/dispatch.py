"""Resolves a destination URI's scheme to an adapter. Fire-and-forget by design
(§9.3: notify is fire-and-forget) — callers should not await this on the critical path."""
import logging

from resolvix.core.notify.adapters import console, email, vobiz, webhook, whatsapp

logger = logging.getLogger("resolvix.notify.dispatch")

_ADAPTERS = {a.scheme: a for a in (console, webhook, whatsapp, email, vobiz)}


async def notify(destination: str, message: str, ticket: dict) -> None:
    scheme = destination.split(":", 1)[0]
    adapter = _ADAPTERS.get(scheme)
    if adapter is None:
        logger.warning("unknown destination scheme=%s, falling back to console", scheme)
        adapter = console
    await adapter.send(destination, message, ticket)
