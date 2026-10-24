"""Per-stage timing (§9.4). Every turn logs one structured line with all stage
timings plus route/answerability/immediacy/cache_hit — `GET /metrics` exposes the
running aggregates. In-process counters only, no external metrics backend (zero
budget, and a restart losing metrics history is an acceptable trade for a demo).
"""
import logging
import time
from collections import defaultdict
from contextlib import contextmanager

logger = logging.getLogger("resolvix.telemetry")

_STAGE_SAMPLES: dict[str, list[float]] = defaultdict(list)
_MAX_SAMPLES_PER_STAGE = 500


@contextmanager
def span(stage: str):
    start = time.monotonic()
    try:
        yield
    finally:
        elapsed_ms = (time.monotonic() - start) * 1000
        samples = _STAGE_SAMPLES[stage]
        samples.append(elapsed_ms)
        if len(samples) > _MAX_SAMPLES_PER_STAGE:
            samples.pop(0)


def _percentile(samples: list[float], p: float) -> float | None:
    if not samples:
        return None
    s = sorted(samples)
    idx = min(len(s) - 1, int(len(s) * p))
    return round(s[idx], 1)


def snapshot() -> dict:
    return {
        stage: {
            "count": len(samples),
            "p50_ms": _percentile(samples, 0.50),
            "p95_ms": _percentile(samples, 0.95),
        }
        for stage, samples in _STAGE_SAMPLES.items()
    }
