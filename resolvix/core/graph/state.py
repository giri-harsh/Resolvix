"""LangGraph session state (§10.1)."""
import time
from typing import Literal, TypedDict


class Turn(TypedDict):
    role: Literal["caller", "agent"]
    text: str
    ts: float
    interrupted: bool
    spoken_prefix: str | None


class RetrievalTrace(TypedDict):
    chunk_ids: list[str]
    scores: list[float]
    queues: list[str]
    lexical_ms: int
    dense_ms: int


class EscalationDecision(TypedDict):
    route: Literal["answer", "clarify", "transfer", "ticket"]
    vector: dict
    immediacy: float
    need_human: float
    thresholds_version: str
    rationale: str
    human_available: bool
    # True when this situation genuinely warranted "transfer" but no human was
    # available for the queue, so it silently fell back to "ticket" — the ticket
    # node uses this to speak an honest urgency-acknowledging line instead of the
    # generic ticket confirmation (§6.5.3's availability gating, made non-silent).
    degraded_from_transfer: bool


class SessionState(TypedDict):
    session_id: str
    channel: str
    agent_id: str | None
    caller_uid: int
    caller_id: str
    domain: str
    language: str
    started_at: float
    turns: list[Turn]
    slots: dict[str, str]
    pending_slot: str | None
    clarify_turns: int
    last_retrieval: RetrievalTrace | None
    urgency_history: list[dict]
    immediacy_ratchet: float
    decision: EscalationDecision | None
    tool_calls: list[dict]
    deadline_spend_ms: int
    breaches: list[str]
    outcome: str | None
    # Not in the PRD's table verbatim — carries the current turn's raw user text
    # through the graph without re-deriving it from `turns` in every node.
    current_utterance: str
    cache_hit_answer: str | None
    # Set by confirm.py, consumed by the shim (core/openai_shim/routes.py) BEFORE
    # the next turn re-enters the graph — a yes/no reply here bypasses
    # retrieve/classify/decide entirely and either executes the frozen route or
    # clears back to a fresh turn (pivot PRD §4's confirm-before-submit node).
    pending_confirmation: dict | None


def new_session(session_id: str, channel: str, domain: str, caller_id: str) -> SessionState:
    return SessionState(
        session_id=session_id,
        channel=channel,
        agent_id=None,
        caller_uid=0,
        caller_id=caller_id,
        domain=domain,
        language="en",
        started_at=time.time(),
        turns=[],
        slots={},
        pending_slot=None,
        clarify_turns=0,
        last_retrieval=None,
        urgency_history=[],
        immediacy_ratchet=0.0,
        decision=None,
        tool_calls=[],
        deadline_spend_ms=0,
        breaches=[],
        outcome=None,
        current_utterance="",
        cache_hit_answer=None,
        pending_confirmation=None,
    )
