"""Ticket + calibration API surface (§11.3). `category` accepted as a deprecated
alias for `queue` — there is no old dashboard depending on it in this rebuild (v1's
department.html was deleted, not ported), so this alias exists only because the PRD
calls for it; harmless to keep for whatever consumes this API next.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from resolvix import settings
from resolvix.core.domain.loader import get_pack
from resolvix.core.routing.calibration import CalibrationEvent, recalibrate
from resolvix.core.tickets.sqlite_store import SqliteTicketStore

router = APIRouter()
_store = SqliteTicketStore()


@router.get("/api/tickets")
def list_tickets(queue: str | None = None, category: str | None = None, status: str | None = None, priority_min: int | None = None, session_id: str | None = None):
    queue = queue or category
    return _store.list_tickets(queue=queue, status=status, priority_min=priority_min, session_id=session_id)


class ManualTicket(BaseModel):
    domain: str
    queue: str
    session_id: str
    channel: str | None = None
    caller_id: str | None = None
    caller_attributes: dict = {}
    summary: str
    transcript: list = []
    intent: str | None = None
    urgency_vector: dict = {}
    immediacy: float = 0.0
    priority: int = 1
    route: str = "ticket"
    sla_due_at: str | None = None


@router.post("/api/tickets", status_code=201)
def create_ticket_manual(body: ManualTicket, idempotency_key: str | None = None):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header/query param required")
    row = _store.create_ticket(idempotency_key=idempotency_key, **body.model_dump())
    return row


class TicketFeedback(BaseModel):
    verdict: str
    labelled_by: str | None = None


@router.post("/api/tickets/{ticket_id}/feedback")
def submit_feedback(ticket_id: str, body: TicketFeedback):
    ticket = _store.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="ticket not found")
    _store.record_feedback(ticket_id, body.verdict, body.labelled_by)
    return {"ok": True}


class StatusUpdate(BaseModel):
    status: str
    resolution: str | None = None


@router.patch("/api/tickets/{ticket_id}/status")
def update_status(ticket_id: str, body: StatusUpdate):
    row = _store.update_status(ticket_id, body.status, body.resolution)
    if not row:
        raise HTTPException(status_code=404, detail="ticket not found")
    return row


@router.get("/api/insights")
def insights():
    return _store.get_insights()


@router.get("/api/thresholds")
def get_thresholds(domain: str = settings.DEFAULT_DOMAIN):
    active = _store.get_active_thresholds(domain)
    pack = get_pack(domain)
    default = pack.thresholds()
    return {
        "active": active,
        "default": {
            "answer_floor": default.answer_floor,
            "human_floor": default.human_floor,
            "immediacy_hi": default.immediacy_hi,
            "max_clarify": default.max_clarify,
        },
    }


@router.post("/api/thresholds/recalibrate")
def recalibrate_thresholds(domain: str = settings.DEFAULT_DOMAIN, activate: bool = False):
    pack = get_pack(domain)
    raw_events = _store.get_calibration_events(domain)
    import json

    events = [CalibrationEvent(vector=json.loads(e["vector"]), actual_route=e["actual_route"], verdict=e["verdict"]) for e in raw_events]
    new_thresholds, cost = recalibrate(events, pack.costs(), pack.thresholds())

    version = f"{domain}@g{len(raw_events)}"
    values = {
        "answer_floor": new_thresholds.answer_floor,
        "human_floor": new_thresholds.human_floor,
        "immediacy_hi": new_thresholds.immediacy_hi,
        "max_clarify": new_thresholds.max_clarify,
    }
    _store.save_thresholds(version, domain, values, len(events), cost, active=activate)
    return {"version": version, "values": values, "n_labels": len(events), "cost": cost, "activated": activate}
