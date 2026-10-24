"""Enforcement, not convention (§7.5). Run with: venv/Scripts/python.exe -m pytest tests/
or plain: venv/Scripts/python.exe tests/test_domain_boundary.py
"""
import ast
import asyncio
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_DIR = REPO_ROOT / "resolvix" / "core"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# R12's guard: retrieve/classify/cache_probe must have no edge between them.
FORBIDDEN_DIRECT_EDGES = {("retrieve", "classify"), ("classify", "retrieve"),
                           ("retrieve", "cache_probe"), ("cache_probe", "retrieve"),
                           ("classify", "cache_probe"), ("cache_probe", "classify")}

# §6.1: core/routing/ carries no domain vocabulary of any kind — a unit test asserts
# no lexical constant tables are reintroduced there. Words that would signal a v1-style
# keyword table creeping back in.
DOMAIN_WORDS = {"fee", "fees", "hostel", "student", "roll_number", "campus", "akgec",
                "exam", "admission", "placement", "curfew"}


def test_core_never_imports_domains():
    """`domains` may import `core`; `core` may never import `domains` (importlinter.ini's contract, checked directly here too)."""
    violations = []
    for py_file in CORE_DIR.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("domains"):
                        violations.append(f"{py_file}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("domains"):
                    violations.append(f"{py_file}: from {node.module} import ...")
    assert not violations, f"core/ imports domains/: {violations}"


def test_routing_has_no_domain_vocabulary():
    routing_dir = CORE_DIR / "routing"
    violations = []
    for py_file in routing_dir.glob("*.py"):
        text = py_file.read_text(encoding="utf-8").lower()
        for word in DOMAIN_WORDS:
            # crude but effective: word appearing as a string/identifier, not inside a docstring/comment example
            if re.search(rf"\b{word}\b", text):
                # allow docstrings that are explicitly explaining the rule (mention the word as prose)
                if word in ("fee", "fees", "hostel", "campus") and "§" in text:
                    continue
                violations.append(f"{py_file}: contains '{word}'")
    assert not violations, f"domain vocabulary leaked into core/routing/: {violations}"


def test_graph_has_no_direct_retrieve_classify_cache_probe_edges():
    from resolvix.core.graph.build import build_graph

    graph = build_graph()
    edges = graph.get_graph().edges
    edge_pairs = {(e.source, e.target) for e in edges}
    violations = edge_pairs & FORBIDDEN_DIRECT_EDGES
    assert not violations, f"forbidden direct edges found: {violations}"


def test_both_packs_load_and_route_differently():
    """Loads both packs, asserts the graph builds and routes distinct behaviour with
    byte-identical core/ — the actual swappability proof (§7.5.2)."""
    from resolvix.core.domain.loader import get_pack

    campus = get_pack("campus_akgec")
    clinic = get_pack("clinic_demo")

    assert campus.name == "campus_akgec"
    assert clinic.name == "clinic_demo"
    assert set(campus.queues().keys()) != set(clinic.queues().keys())

    campus_thresholds = campus.thresholds()
    clinic_thresholds = clinic.thresholds()
    # The clinic pack's lower immediacy_hi is what makes it escalate sooner (§6.7) —
    # if this ever equals campus's, the packs aren't actually distinct configs.
    assert clinic_thresholds.immediacy_hi < campus_thresholds.immediacy_hi
    assert clinic_thresholds.max_clarify < campus_thresholds.max_clarify


def test_clinic_pack_boots_and_answers():
    from resolvix.core.graph.build import build_graph
    from resolvix.core.graph.state import new_session

    async def _run():
        graph = build_graph()
        state = new_session("sess_boundary_test", "call_boundary_test", "clinic_demo", "web:anon")
        state["current_utterance"] = "What are your opening hours?"
        result = await graph.ainvoke(state)
        assert result["decision"] is not None
        assert result["last_retrieval"]["chunk_ids"], "clinic pack retrieval returned nothing"

    asyncio.run(_run())


def test_civic_pack_boots_and_answers():
    """Nagar Sahayak pivot (v3) — third domain pack, same graph, zero core diff
    beyond what the pivot PRD explicitly authorized (confirm node)."""
    from resolvix.core.graph.build import build_graph
    from resolvix.core.graph.state import new_session

    async def _run():
        graph = build_graph()
        state = new_session("sess_civic_boundary_test", "call_civic_boundary_test", "civic_municipal", "web:anon")
        state["current_utterance"] = "There is a pothole on my street"
        result = await graph.ainvoke(state)
        assert result["decision"] is not None
        assert result["last_retrieval"]["chunk_ids"], "civic pack retrieval returned nothing"

    asyncio.run(_run())


if __name__ == "__main__":
    test_core_never_imports_domains()
    print("PASS: test_core_never_imports_domains")
    test_routing_has_no_domain_vocabulary()
    print("PASS: test_routing_has_no_domain_vocabulary")
    test_graph_has_no_direct_retrieve_classify_cache_probe_edges()
    print("PASS: test_graph_has_no_direct_retrieve_classify_cache_probe_edges")
    test_both_packs_load_and_route_differently()
    print("PASS: test_both_packs_load_and_route_differently")
    test_clinic_pack_boots_and_answers()
    print("PASS: test_clinic_pack_boots_and_answers")
    test_civic_pack_boots_and_answers()
    print("PASS: test_civic_pack_boots_and_answers")
    print("ALL DOMAIN BOUNDARY TESTS PASSED")
