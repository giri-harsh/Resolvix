"""StateGraph assembly (§4.1's box diagram, §5.1's turn lifecycle). Nodes are
domain-blind — every node reads the active pack via core.domain.loader, never a
hardcoded domain name.

Deliberate scope cut: this compiled graph produces the ROUTING DECISION and, for
clarify/transfer/ticket/cache-hit-answer, the final spoken text — all non-streaming,
sub-200ms work. A genuinely fresh (non-cached) answer's token-by-token generation
happens OUTSIDE this graph, directly in core/openai_shim/routes.py, because wiring
true incremental SSE delivery through LangGraph's own streaming API with per-turn
cancellation (§5.4b) reliably was more scope than this pass could safely absorb
without risking a subtly broken cancellation path. The routing/decision logic below
is the real thing; only the final answer leaf's *delivery mechanism* is external.
retrieve/classify/cache_probe have no edge between each other (R12's guard).
"""
from langgraph.graph import END, StateGraph

from resolvix.core.graph.nodes.answer import answer
from resolvix.core.graph.nodes.cache_probe import cache_probe
from resolvix.core.graph.nodes.classify import classify
from resolvix.core.graph.nodes.clarify import clarify
from resolvix.core.graph.nodes.confirm import confirm
from resolvix.core.graph.nodes.decide import decide
from resolvix.core.graph.nodes.finalize import finalize
from resolvix.core.graph.nodes.hydrate import hydrate
from resolvix.core.graph.nodes.retrieve import retrieve
from resolvix.core.graph.state import SessionState


def _route_selector(state: SessionState) -> str:
    decision = state.get("decision") or {}
    route = decision.get("route", "ticket")
    # Confirm-before-submit (pivot v3 §4): ticket/transfer never execute directly
    # off this decision — they go through confirm first. The actual ticket/
    # transfer execution on a confirmed "yes" happens via a direct function call
    # from the shim (core/openai_shim/routes.py), not through this graph edge —
    # same pattern already used for the <NG> control-token re-route.
    if route in ("ticket", "transfer"):
        return "confirm"
    return route


def build_graph():
    g = StateGraph(SessionState)

    g.add_node("hydrate", hydrate)
    g.add_node("retrieve", retrieve)
    g.add_node("classify", classify)
    g.add_node("cache_probe", cache_probe)
    g.add_node("decide", decide)
    g.add_node("answer", answer)
    g.add_node("clarify", clarify)
    g.add_node("confirm", confirm)
    g.add_node("finalize", finalize)

    g.set_entry_point("hydrate")

    # Fan-out: no edge directly between retrieve/classify/cache_probe.
    g.add_edge("hydrate", "retrieve")
    g.add_edge("hydrate", "classify")
    g.add_edge("hydrate", "cache_probe")

    # Fan-in.
    g.add_edge("retrieve", "decide")
    g.add_edge("classify", "decide")
    g.add_edge("cache_probe", "decide")

    g.add_conditional_edges(
        "decide",
        _route_selector,
        {"answer": "answer", "clarify": "clarify", "confirm": "confirm"},
    )

    g.add_edge("answer", "finalize")
    g.add_edge("clarify", "finalize")
    g.add_edge("confirm", "finalize")
    g.add_edge("finalize", END)

    return g.compile()


_compiled = None


def get_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled
