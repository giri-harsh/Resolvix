"""classify: urgency vector extraction, runs concurrently with retrieve/cache_probe
(§9.2 row 5c). No edge to/from retrieve — R12 guards against that creeping back in.
"""
from resolvix.core.domain.loader import get_pack
from resolvix.core.graph.state import SessionState
from resolvix.core.routing.classifier import classify as run_classifier
from resolvix.core.telemetry.spans import span


async def classify(state: SessionState) -> dict:
    pack = get_pack(state["domain"])
    # All exemplars are inlined rather than retrieving the nearest few by embedding
    # (§6.5.1's "retrieved rubric anchors") — the campus pack has 8 total, small
    # enough that a nearest-neighbour lookup buys nothing yet. Revisit once a pack's
    # exemplar set grows past a few dozen.
    exemplars_text = "\n".join(f'- "{e.text}" -> {e.vector}' for e in pack.exemplars())
    preamble = pack.classify_preamble()

    with span("classify"):
        vector = await run_classifier(state["current_utterance"], exemplars_text, preamble)
    history = state.get("urgency_history", []) + [vector.model_dump()]
    return {"urgency_history": history}
