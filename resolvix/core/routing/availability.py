"""On-shift lookup — a runtime input to the policy, not an axis of the vector (§6.5.3).
In-process registry for now; Phase 4's WS /ws/agents presence channel updates it as
staff connect/disconnect. No persistence — a restart means every queue reads
unavailable until someone reconnects, which is the safe default (never overclaim a
human is there).
"""
_AVAILABLE_QUEUES: set[str] = set()


def set_available(queue: str, available: bool) -> None:
    if available:
        _AVAILABLE_QUEUES.add(queue)
    else:
        _AVAILABLE_QUEUES.discard(queue)


def is_available(queue: str) -> bool:
    return queue in _AVAILABLE_QUEUES
