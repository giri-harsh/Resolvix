"""The decision surface (§6.4). Domain-free by construction — every constant comes
from the active pack's escalation.yaml Thresholds; nothing here names a domain
concept. A test in tests/test_domain_boundary.py asserts no lexical constant tables
creep back in.
"""
from dataclasses import dataclass
from typing import Literal

Route = Literal["answer", "clarify", "transfer", "ticket"]


@dataclass
class Thresholds:
    answer_floor: float = 0.55
    human_floor: float = 0.50
    immediacy_hi: float = 0.62
    max_clarify: int = 2


def compute_need_human(human_authority_required: float, answerability: float) -> float:
    return max(human_authority_required, 1.0 - answerability)


def compute_immediacy(time_criticality: float, blocking: float, harm_if_delayed: float) -> float:
    return 0.50 * time_criticality + 0.30 * blocking + 0.20 * harm_if_delayed


def decide(
    *,
    answerability: float,
    human_authority_required: float,
    time_criticality: float,
    blocking: float,
    harm_if_delayed: float,
    clarify_turns: int,
    thresholds: Thresholds,
    human_available: bool,
) -> tuple[Route, float, float, bool]:
    """Returns (route, immediacy, need_human, degraded_from_transfer).

    degraded_from_transfer is True when the situation genuinely warranted a live
    transfer (need_human and immediacy both cleared threshold) but no human was
    available, so the route silently fell back to "ticket" — the caller should be
    told this out loud rather than getting the same generic ticket line as a
    routine, non-urgent ticket (§6.5.3's availability gating was correct; staying
    silent about *why* it degraded was the actual bug)."""
    need_human = compute_need_human(human_authority_required, answerability)
    immediacy = compute_immediacy(time_criticality, blocking, harm_if_delayed)
    degraded_from_transfer = False

    if answerability >= thresholds.answer_floor and immediacy < thresholds.immediacy_hi:
        route: Route = "answer"
    elif need_human >= thresholds.human_floor and immediacy >= thresholds.immediacy_hi:
        if human_available:
            route = "transfer"
        else:
            route = "ticket"
            degraded_from_transfer = True
    elif need_human >= thresholds.human_floor:
        route = "ticket"
    elif clarify_turns < thresholds.max_clarify:
        route = "clarify"
    else:
        route = "ticket"

    return route, immediacy, need_human, degraded_from_transfer
