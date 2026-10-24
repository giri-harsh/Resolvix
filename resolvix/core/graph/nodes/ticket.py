"""ticket: create a ticket, fire-and-forget notify, spoken ID confirmation (§5.5, §10.2).

idempotency_key is keyed on session_id alone (not per-turn) — a barge-in-cancelled
retry within the same session must not create a second ticket (§5.4b, R10); the
UNIQUE index on idempotency_key makes create_ticket a safe no-op replay.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from resolvix.core.domain.loader import get_pack
from resolvix.core.graph.nodes._shared import resolve_queue
from resolvix.core.graph.state import SessionState
from resolvix.core.notify.dispatch import notify
from resolvix.core.tickets.sqlite_store import SqliteTicketStore

_store = SqliteTicketStore()


def _priority_from_immediacy(immediacy: float) -> int:
    if immediacy < 0.25:
        return 0
    if immediacy < 0.5:
        return 1
    if immediacy < 0.75:
        return 2
    return 3


def _spoken_digits(ticket_id: str) -> str:
    return " ".join(ticket_id)


def _sla_to_plain_language(sla_minutes: int) -> str:
    """Pivot v3 §6 — case reference + next-step line. sla_minutes is already in
    domain.yaml: queues; this is a template/formatting change, not new data."""
    if sla_minutes < 60:
        return f"within {sla_minutes} minutes"
    if sla_minutes < 1440:
        hours = round(sla_minutes / 60)
        return f"within {hours} hour{'s' if hours != 1 else ''}"
    days = round(sla_minutes / 1440)
    return f"within {days} day{'s' if days != 1 else ''}"


async def ticket(state: SessionState) -> dict:
    pack = get_pack(state["domain"])
    queue_key = resolve_queue(state, pack)
    queue = pack.queues().get(queue_key)
    decision = state.get("decision") or {}
    immediacy = decision.get("immediacy", 0.0)
    priority = _priority_from_immediacy(immediacy)

    sla_minutes = queue.sla_minutes if queue else 480
    sla_due_at = (datetime.now(timezone.utc) + timedelta(minutes=sla_minutes)).isoformat()

    degraded_from_transfer = decision.get("degraded_from_transfer", False)
    # Distinct stored route so a degraded-transfer ticket is queryable separately
    # from a routine one — same value PRD §10.2 already uses for the transfer-
    # timeout case in core/transport/transfer_ws.py, since both mean "this needed
    # a human and didn't get one," just via different failure paths.
    stored_route = "transfer_failed" if degraded_from_transfer else decision.get("route", "ticket")

    row = _store.create_ticket(
        domain=state["domain"],
        queue=queue_key,
        session_id=state["session_id"],
        channel=state.get("channel"),
        caller_id=state.get("caller_id"),
        caller_attributes=state.get("slots", {}),
        summary=state["current_utterance"][:280],
        transcript=state.get("turns", []),
        intent=queue_key,
        urgency_vector=decision.get("vector", {}),
        immediacy=immediacy,
        priority=priority,
        route=stored_route,
        sla_due_at=sla_due_at,
        idempotency_key=f"{state['session_id']}:ticket",
    )

    if queue and queue.destinations:
        urgent_tag = " [URGENT — no operator was available]" if degraded_from_transfer else ""
        message = f"New ticket {row['id']} ({queue_key}, priority {priority}){urgent_tag}: {row['summary']}"
        for destination in queue.destinations:
            asyncio.create_task(notify(destination, message, row))

    if degraded_from_transfer:
        # §6.5.3's availability gating was already correct — this just stops it
        # from being silent about *why* it degraded (the actual bug reported).
        outcome = (
            f"This sounds urgent and I don't have anyone free to take the call right now, "
            f"so I've logged it as a priority ticket, {_spoken_digits(row['id'])} — "
            f"someone will call you back as soon as possible."
        )
    else:
        queue_label = queue.label if queue else queue_key
        eta = _sla_to_plain_language(sla_minutes)
        outcome = (
            f"Logged as case {_spoken_digits(row['id'])} — {queue_label} team, "
            f"typical resolution {eta}. You'll get a callback on this number."
        )
    return {"outcome": outcome, "tool_calls": state.get("tool_calls", []) + [
        {"tool": "create_ticket", "args": {"queue": queue_key}, "idempotency_key": f"{state['session_id']}:ticket", "result": row["id"]}
    ]}
