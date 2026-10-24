"""No-op destination — logs only. Always free, always available, used as the
`general` queue's default and as the ultimate degradation-ladder fallback."""
import logging

logger = logging.getLogger("resolvix.notify.console")

scheme = "console"


async def send(target: str, message: str, ticket: dict) -> None:
    logger.info("[console notify] ticket=%s: %s", ticket.get("id"), message)
