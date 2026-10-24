"""hydrate: load/create SessionState, stamp the current turn's utterance (§9.2 row 4)."""
from resolvix.core.graph.state import SessionState


async def hydrate(state: SessionState) -> SessionState:
    return state
