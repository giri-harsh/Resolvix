"""finalize: append the outcome turn, spill to SQLite (§10.1), log the query."""
import time

from resolvix.core.graph.state import SessionState
from resolvix.core.session.store import get_store
from resolvix.core.tickets.sqlite_store import SqliteTicketStore

_ticket_store = SqliteTicketStore()


async def finalize(state: SessionState) -> dict:
    turns = list(state.get("turns", []))
    if state.get("outcome"):
        turns.append({
            "role": "agent",
            "text": state["outcome"],
            "ts": time.time(),
            "interrupted": False,
            "spoken_prefix": None,
        })

    decision = state.get("decision") or {}
    _ticket_store.log_query(
        domain=state["domain"],
        queue=None,
        query=state.get("current_utterance"),
        answered=decision.get("route") == "answer",
        route=decision.get("route"),
        answerability=decision.get("vector", {}).get("answerability"),
        immediacy=decision.get("immediacy"),
        cache_hit=bool(state.get("cache_hit_answer")),
        first_audio_ms=state.get("first_audio_ms"),
    )

    new_state = {**state, "turns": turns}
    get_store().spill(new_state)
    return {"turns": turns}
