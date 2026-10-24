"""Ticket-related routes."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, status as http_status, Request
from resolvix_contracts import TicketCreate, TicketCreated, Ticket as TicketContract, TicketPatch, TicketEvent as TicketEventContract
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..deps import get_db, get_principal
from ..orm import Ticket, TicketSeq, TicketEvent
from ..privacy import mask_number
from ..sse import hub as sse_hub

router = APIRouter(prefix="/v1", tags=["tickets"])


def allocate_ticket_id(db: Session, department_prefix: str) -> str:
    """Allocate next ticket ID atomically (BEGIN IMMEDIATE handles concurrency)."""
    # Get and increment sequence
    seq = db.query(TicketSeq).filter(TicketSeq.id == 1).with_for_update().first()
    if not seq:
        seq = TicketSeq(id=1, next_num=1001)
        db.add(seq)
        db.flush()
    
    ticket_num = seq.next_num
    seq.next_num += 1
    db.flush()
    
    return f"{department_prefix}-{ticket_num:04d}"


@router.post("/tickets", status_code=201)
def create_ticket(
    request: Request,
    ticket_create: TicketCreate,
    db: Session = Depends(get_db),
    principal: dict = Depends(get_principal)
):
    """Create ticket (A). Idempotent on idempotency_key."""
    # Check for duplicate (idempotency)
    existing = db.query(Ticket).filter(Ticket.idempotency_key == ticket_create.idempotency_key).first()
    if existing:
        # Return original ticket ID without consuming a new sequence number
        return TicketCreated(ticket_id=existing.ticket_id, created=False).model_dump(mode="json")
    
    # Validate department exists
    departments_config = request.app.state.departments_config
    dept_map = {d.key: d for d in departments_config.departments}
    
    if ticket_create.department not in dept_map:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown department: {ticket_create.department}"
        )
    
    # Allocate ticket ID
    dept = dept_map[ticket_create.department]
    ticket_id = allocate_ticket_id(db, dept.ticket_prefix)
    
    # Create ticket
    ticket = Ticket(
        ticket_id=ticket_id,
        idempotency_key=ticket_create.idempotency_key,
        call_id=ticket_create.call_id,
        type=ticket_create.type,
        priority=ticket_create.priority,
        priority_reason=ticket_create.priority_reason,
        rule_id=None,  # Extract from priority_reason if needed (format: "R-XXX: reason")
        department=ticket_create.department,
        status="open",
        summary=ticket_create.summary,
        collected_fields=ticket_create.collected_fields,
        caller_number=ticket_create.caller_number,
        callback_number=ticket_create.callback_number,
        callback_requested=ticket_create.callback_requested,
        transcript_excerpt=ticket_create.transcript_excerpt,
        brief=ticket_create.brief,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    # Extract rule_id from priority_reason if it starts with "R-"
    if ticket_create.priority_reason.startswith("R-"):
        rule_id = ticket_create.priority_reason.split(":")[0].strip()
        ticket.rule_id = rule_id
    
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    
    # Publish SSE events (after commit)
    sse_hub.publish("ticket.created", {
        "ticket_id": ticket_id,
        "type": ticket_create.type,
        "priority": ticket_create.priority,
        "department": ticket_create.department,
        "summary": ticket_create.summary,
        "caller_number": mask_number(ticket_create.caller_number),
        "callback_number": mask_number(ticket_create.callback_number)
    })
    
    # P1 alert
    if ticket_create.priority == "P1":
        sse_hub.publish("alert.p1", {
            "ticket_id": ticket_id,
            "department": ticket_create.department,
            "priority": ticket_create.priority,
            "priority_reason": ticket_create.priority_reason,
            "rule_id": ticket.rule_id,
            "caller_number": mask_number(ticket_create.caller_number)
        })
    
    return TicketCreated(ticket_id=ticket_id, created=True).model_dump(mode="json")


@router.get("/tickets")
def list_tickets(
    status: Optional[str] = None,
    department: Optional[str] = None,
    priority: Optional[str] = None,
    caller_number: Optional[str] = None,
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
    principal: dict = Depends(get_principal)
):
    """List tickets (dashboard). Sorted by priority (P1 first) then newest first."""
    query = db.query(Ticket)
    
    if status:
        query = query.filter(Ticket.status == status)
    
    if department:
        query = query.filter(Ticket.department == department)
    
    if priority:
        query = query.filter(Ticket.priority == priority)
    
    if caller_number:
        # Exact match on full number
        query = query.filter(Ticket.caller_number == caller_number)
    
    # Sort: P1 -> P4, then newest first
    priority_order = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}
    tickets = query.all()
    
    # Sort in Python (SQLite doesn't have CASE-based enum ordering easily)
    tickets.sort(key=lambda t: (priority_order.get(t.priority, 5), -t.id))
    
    # Apply limit
    tickets = tickets[:limit]
    
    # Build response (masked numbers)
    items = []
    for ticket in tickets:
        items.append({
            "ticket_id": ticket.ticket_id,
            "call_id": ticket.call_id,
            "type": ticket.type,
            "priority": ticket.priority,
            "priority_reason": ticket.priority_reason,
            "department": ticket.department,
            "status": ticket.status,
            "summary": ticket.summary,
            "caller_number": mask_number(ticket.caller_number),
            "callback_number": mask_number(ticket.callback_number),
            "callback_requested": ticket.callback_requested,
            "brief": ticket.brief,
            "assignee": ticket.assignee,
            "created_at": ticket.created_at.isoformat(),
            "updated_at": ticket.updated_at.isoformat(),
            "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None
        })
    
    return {"items": items}


@router.get("/tickets/{ticket_id}")
def get_ticket_detail(
    ticket_id: str,
    reveal: bool = Query(False),
    db: Session = Depends(get_db),
    principal: dict = Depends(get_principal)
):
    """Get ticket detail. Supports reveal=true for full numbers."""
    ticket = db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
    if not ticket:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found"
        )
    
    # Mask or reveal numbers
    caller_number = ticket.caller_number if reveal else mask_number(ticket.caller_number)
    callback_number = ticket.callback_number if reveal else mask_number(ticket.callback_number)
    
    # Audit reveal action
    actor = principal.get("email", "service")
    if reveal and (ticket.caller_number or ticket.callback_number):
        write_audit(db, actor, "number_revealed", "ticket", ticket_id, {
            "fields": "caller_number,callback_number"
        })
        db.commit()
    
    # Build response
    return {
        "ticket_id": ticket.ticket_id,
        "call_id": ticket.call_id,
        "type": ticket.type,
        "priority": ticket.priority,
        "priority_reason": ticket.priority_reason,
        "rule_id": ticket.rule_id,
        "department": ticket.department,
        "status": ticket.status,
        "summary": ticket.summary,
        "collected_fields": ticket.collected_fields,
        "caller_number": caller_number,
        "callback_number": callback_number,
        "callback_requested": ticket.callback_requested,
        "transcript_excerpt": ticket.transcript_excerpt,
        "brief": ticket.brief,
        "assignee": ticket.assignee,
        "notes": ticket.notes,
        "created_at": ticket.created_at.isoformat(),
        "updated_at": ticket.updated_at.isoformat(),
        "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None
    }


@router.patch("/tickets/{ticket_id}")
def update_ticket(
    request: Request,
    ticket_id: str,
    patch: TicketPatch,
    db: Session = Depends(get_db),
    principal: dict = Depends(get_principal)
):
    """Update ticket (dashboard). Calls notifier on status change."""
    ticket = db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
    if not ticket:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found"
        )
    
    actor = principal.get("email", "service")
    old_status = ticket.status
    status_changed = False
    
    # Apply patch
    if patch.status is not None:
        if patch.status != ticket.status:
            status_changed = True
            ticket.status = patch.status
            
            # Update resolved_at if status is resolved
            if patch.status == "resolved":
                ticket.resolved_at = datetime.utcnow()
    
    if patch.assignee is not None:
        ticket.assignee = patch.assignee
    
    if patch.note:
        # Append note with timestamp and actor
        timestamp = datetime.utcnow().isoformat()
        note_entry = f"[{timestamp}] {actor}: {patch.note}"
        if ticket.notes is None:
            ticket.notes = []
        ticket.notes = list(ticket.notes) + [note_entry]  # Create new list for SQLAlchemy to detect change
        
        # Add ticket event
        event = TicketEvent(
            ticket_id=ticket_id,
            kind="note_added",
            payload={"note": patch.note},
            actor=actor,
            at=datetime.utcnow()
        )
        db.add(event)
    
    ticket.updated_at = datetime.utcnow()
    
    # Write audit
    audit_details = {}
    if patch.status:
        audit_details["status"] = f"{old_status} -> {patch.status}"
    if patch.assignee:
        audit_details["assignee"] = patch.assignee
    if patch.note:
        audit_details["note_added"] = "yes"
    
    write_audit(db, actor, "ticket_updated", "ticket", ticket_id, audit_details)
    
    # Add status_changed event if status changed
    if status_changed:
        event = TicketEvent(
            ticket_id=ticket_id,
            kind="status_changed",
            payload={"old_status": old_status, "new_status": ticket.status},
            actor=actor,
            at=datetime.utcnow()
        )
        db.add(event)
    
    db.commit()
    db.refresh(ticket)
    
    # Call notifier if status changed (after commit)
    if status_changed:
        notifier = request.app.state.notifier
        notifier.on_ticket_status_changed(db, ticket, old_status, ticket.status, actor)
    
    # Publish SSE event (after commit and notifier)
    sse_hub.publish("ticket.updated", {
        "ticket_id": ticket_id,
        "status": ticket.status,
        "assignee": ticket.assignee,
        "updated_at": ticket.updated_at.isoformat()
    })
    
    # Return full ticket (masked numbers)
    return get_ticket_detail(ticket_id, reveal=False, db=db, principal=principal)


@router.post("/tickets/{ticket_id}/events", status_code=201)
def add_ticket_event(
    ticket_id: str,
    event: TicketEventContract,
    db: Session = Depends(get_db),
    principal: dict = Depends(get_principal)
):
    """Append a ticket event (A)."""
    # Check ticket exists
    ticket = db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
    if not ticket:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found"
        )
    
    # Create event
    db_event = TicketEvent(
        ticket_id=ticket_id,
        kind=event.kind,
        payload=event.payload,
        actor=event.actor,
        at=event.at
    )
    db.add(db_event)
    db.commit()
    
    return {"status": "ok"}


@router.get("/tickets/{ticket_id}/events")
def list_ticket_events(
    ticket_id: str,
    db: Session = Depends(get_db),
    principal: dict = Depends(get_principal)
):
    """Get ticket events (oldest first)."""
    # Check ticket exists
    ticket = db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
    if not ticket:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found"
        )
    
    events = db.query(TicketEvent).filter(TicketEvent.ticket_id == ticket_id).order_by(TicketEvent.at).all()
    
    items = []
    for event in events:
        items.append({
            "kind": event.kind,
            "payload": event.payload,
            "actor": event.actor,
            "at": event.at.isoformat()
        })
    
    return {"items": items}
