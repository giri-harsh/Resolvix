"""decide: picks a speculative route from the fan-in of retrieve/classify/cache_probe
(§9.2 row 6). "Speculative" because full confirmation of answerability only arrives
at the answer node's first token (§6.3) — a <NG> there re-routes via decide() a
second time, called directly from answer.py rather than via a graph cycle (kept the
graph itself a single forward pass; see answer.py for why).
"""
from resolvix.core.domain.loader import get_pack
from resolvix.core.graph.state import EscalationDecision, SessionState
from resolvix.core.routing import availability
from resolvix.core.routing.policy import decide as policy_decide

# Empirical scale factor mapping our RRF fusion scores (observed ~0.02-0.04 for a
# good hybrid match on this corpus size) into the 0-1 range decide() needs. Not
# calibrated against a real eval suite (that's `make bench`, not built this pass) —
# revisit once real query logs exist.
RRF_SCALE = 20.0


def normalize_retrieval_score(score: float) -> float:
    return min(1.0, score * RRF_SCALE)


def estimate_answerability(state: SessionState, pack) -> tuple[float, str | None]:
    trace = state.get("last_retrieval")
    if not trace or not trace["scores"]:
        return 0.0, None
    top_score = trace["scores"][0]
    top_chunk_id = trace["chunk_ids"][0]
    chunk = pack.retriever().get_chunk(top_chunk_id)
    answerability = normalize_retrieval_score(top_score)
    if chunk and chunk.provenance == "synthetic":
        answerability = max(0.0, answerability - pack.synthetic_answerability_penalty())
    return answerability, (chunk.queue if chunk else None)


async def decide(state: SessionState) -> dict:
    pack = get_pack(state["domain"])
    thresholds = pack.thresholds()

    answerability, queue = estimate_answerability(state, pack)
    queue = queue or "general"

    latest_vector = (state.get("urgency_history") or [{}])[-1]
    human_available = availability.is_available(queue)

    route, immediacy, need_human, degraded_from_transfer = policy_decide(
        answerability=answerability,
        human_authority_required=latest_vector.get("human_authority_required", 0.0),
        time_criticality=latest_vector.get("time_criticality", 0.0),
        blocking=latest_vector.get("blocking", 0.0),
        harm_if_delayed=latest_vector.get("harm_if_delayed", 0.0),
        clarify_turns=state.get("clarify_turns", 0),
        thresholds=thresholds,
        human_available=human_available,
    )

    # Immediacy ratchet (§6.6): never de-escalated by a calmer follow-up sentence.
    ratchet = max(state.get("immediacy_ratchet", 0.0), immediacy)

    if state.get("cache_hit_answer"):
        route = "answer"  # cache hit short-circuits straight to answer (already-known-good text)

    decision = EscalationDecision(
        route=route,
        vector={**latest_vector, "answerability": answerability},
        immediacy=immediacy,
        need_human=need_human,
        thresholds_version=f"{pack.name}@default",
        rationale=latest_vector.get("rationale", ""),
        human_available=human_available,
        degraded_from_transfer=degraded_from_transfer,
    )
    return {"decision": decision, "immediacy_ratchet": ratchet}
