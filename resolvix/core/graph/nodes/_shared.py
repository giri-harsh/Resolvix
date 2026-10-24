"""Small helpers shared across graph nodes — not a node itself."""
from resolvix.core.graph.state import SessionState


def resolve_queue(state: SessionState, pack) -> str:
    trace = state.get("last_retrieval")
    if trace and trace["chunk_ids"]:
        chunk = pack.retriever().get_chunk(trace["chunk_ids"][0])
        if chunk:
            return chunk.queue
    return "general"
