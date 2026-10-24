"""Destination contract — a queue's notification target is a URI (e.g. `whatsapp:+91...`,
`webhook:https://...`, `console:`), resolved to an adapter by scheme. Core never
constructs a destination string itself; domain packs supply them in escalation.yaml.
"""
from typing import Protocol


class Destination(Protocol):
    scheme: str

    async def send(self, target: str, message: str, ticket: dict) -> None: ...
