"""transfer: narrate the handoff and hand off to Phase 4's live-transfer machinery.
Availability gating already happened in policy.py (decide only routes here when a
human is available for the queue) — this node's job is just the spoken commitment;
core/transport's transfer endpoint (Phase 4) does the actual channel handoff.
"""
from resolvix.core.domain.loader import get_pack
from resolvix.core.graph.nodes._shared import resolve_queue
from resolvix.core.graph.state import SessionState

NARRATION = "Staying on the line with you — connecting you now."


async def transfer(state: SessionState) -> dict:
    pack = get_pack(state["domain"])
    queue = resolve_queue(state, pack)
    return {"outcome": NARRATION, "pending_slot": None, "tool_calls": state.get("tool_calls", []) + [
        {"tool": "transfer", "args": {"queue": queue}, "idempotency_key": f"{state['session_id']}:transfer"}
    ]}
