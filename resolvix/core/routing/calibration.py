"""Online threshold calibration from human feedback (§6.5.2). Grid search over the
three policy thresholds to minimise an asymmetric cost — cheap enough (a few hundred
stored vectors, three scalars) that no training infrastructure is justified.
"""
from dataclasses import dataclass

from resolvix.core.routing.policy import Thresholds, decide

MIN_LABELS_TO_CALIBRATE = 20

# Grid resolution — coarse is fine; explainability matters more than precision here.
_GRID = [round(0.30 + 0.05 * i, 2) for i in range(13)]  # 0.30 .. 0.90


@dataclass
class CostWeights:
    c_false_transfer: float = 3.0
    c_missed_transfer: float = 5.0
    c_wrong_answer: float = 4.0
    c_needless_ticket: float = 1.0


@dataclass
class CalibrationEvent:
    vector: dict  # frozen UrgencyVector + answerability, as stored at decision time
    actual_route: str
    verdict: str  # correct | should_have_transferred | should_have_ticketed | should_have_been_answered


def _cost(events: list[CalibrationEvent], thresholds: Thresholds, costs: CostWeights, human_available: bool = True) -> float:
    total = 0.0
    for ev in events:
        v = ev.vector
        route, _, _, _ = decide(
            answerability=v.get("answerability", 0.0),
            human_authority_required=v.get("human_authority_required", 0.0),
            time_criticality=v.get("time_criticality", 0.0),
            blocking=v.get("blocking", 0.0),
            harm_if_delayed=v.get("harm_if_delayed", 0.0),
            clarify_turns=v.get("clarify_turns", 0),
            thresholds=thresholds,
            human_available=human_available,
        )
        if ev.verdict == "should_have_transferred" and route != "transfer":
            total += costs.c_missed_transfer
        elif ev.verdict == "should_have_ticketed" and route == "transfer":
            total += costs.c_false_transfer
        elif ev.verdict == "should_have_been_answered" and route != "answer":
            total += costs.c_wrong_answer
        elif ev.verdict == "correct" and route == "ticket" and v.get("answerability", 0) > 0.7:
            total += costs.c_needless_ticket
    return total


def recalibrate(events: list[CalibrationEvent], costs: CostWeights, base: Thresholds) -> tuple[Thresholds, float]:
    """Grid search over (answer_floor, human_floor, immediacy_hi); max_clarify is
    left as-is — it's a UX knob, not a cost-driven one."""
    if len(events) < MIN_LABELS_TO_CALIBRATE:
        return base, _cost(events, base, costs)

    best_thresholds, best_cost = base, _cost(events, base, costs)
    for answer_floor in _GRID:
        for human_floor in _GRID:
            for immediacy_hi in _GRID:
                candidate = Thresholds(
                    answer_floor=answer_floor,
                    human_floor=human_floor,
                    immediacy_hi=immediacy_hi,
                    max_clarify=base.max_clarify,
                )
                cost = _cost(events, candidate, costs)
                if cost < best_cost:
                    best_thresholds, best_cost = candidate, cost
    return best_thresholds, best_cost
