"""clarify: ambiguity -> a one-breath question templated from the competing
candidates (§5.3). At most two per issue — enforced by policy.py's max_clarify.

Options are built from the candidates' QUEUE LABELS (domain.yaml's short,
human-written labels), not raw chunk headings. Live bug: this corpus's `##`
headings are long, full-sentence prose ("What this means for a specific
application (e.g., a certificate or a civic complaint)"), not short topic
names like campus_akgec's ("Hostel Fee") — dropping those verbatim into
"Is that about X or Y?" produced a broken-sounding run-on. Queue labels are
short by construction (domain.yaml authors them as a display label), so this
approach is robust to whatever a given pack's corpus prose actually looks like.
"""
from resolvix.core.domain.loader import get_pack
from resolvix.core.graph.state import SessionState

FALLBACK_TEXT = "Could you tell me a little more about what you need?"


async def clarify(state: SessionState) -> dict:
    pack = get_pack(state["domain"])
    trace = state.get("last_retrieval")
    queues = pack.queues()

    labels: list[str] = []
    if trace:
        for chunk_id in trace["chunk_ids"]:
            chunk = pack.retriever().get_chunk(chunk_id)
            if not chunk:
                continue
            queue = queues.get(chunk.queue)
            label = queue.label if queue else chunk.queue
            if label not in labels:
                labels.append(label)
            if len(labels) >= 2:
                break

    if len(labels) < 2:
        text = FALLBACK_TEXT
    else:
        text = pack.clarify_prompt(" or ".join(labels[:2]))
    return {"outcome": text, "clarify_turns": state.get("clarify_turns", 0) + 1}
