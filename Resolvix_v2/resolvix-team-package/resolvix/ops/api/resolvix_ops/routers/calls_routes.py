"""Call-related routes."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, status as http_status
from resolvix_contracts import CallStart, CallEnd, TurnSummary, ErrorEnvelope, ErrorBody
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..deps import get_db, get_principal
from ..orm import Call, Turn
from ..privacy import mask_number
from ..sse import hub as sse_hub

router = APIRouter(prefix="/v1", tags=["calls"])


@router.post("/calls", status_code=201)
def register_call(
    call_start: CallStart,
    db: Session = Depends(get_db),
    principal: dict = Depends(get_principal)
):
    """Register a call at start (A). Idempotent on call_id."""
    # Check if call already exists
    existing = db.query(Call).filter(Call.call_id == call_start.call_id).first()
    if existing:
        # Idempotent: already registered
        return {"status": "ok", "created": False}
    
    # Create new call
    call = Call(
        call_id=call_start.call_id,
        channel=call_start.channel,
        caller_number=call_start.caller_number,
        started_at=call_start.started_at,
        kb_version=call_start.kb_version,
        lang=call_start.lang,
        turns_count=0
    )
    db.add(call)
    db.commit()
    
    # Publish SSE event (after commit)
    sse_hub.publish("call.started", {
        "call_id": call_start.call_id,
        "channel": call_start.channel,
        "caller_number": mask_number(call_start.caller_number),
        "started_at": call_start.started_at.isoformat(),
        "kb_version": call_start.kb_version,
        "lang": call_start.lang
    })
    
    return {"status": "ok", "created": True}


@router.get("/calls")
def list_calls(
    from_: Optional[datetime] = Query(None, alias="from"),
    outcome: Optional[str] = None,
    limit: int = Query(50, le=1000),
    db: Session = Depends(get_db),
    principal: dict = Depends(get_principal)
):
    """List calls (dashboard)."""
    query = db.query(Call)
    
    if from_:
        query = query.filter(Call.started_at >= from_)
    
    if outcome:
        query = query.filter(Call.outcome == outcome)
    
    # Order by newest first
    query = query.order_by(desc(Call.started_at))
    
    # Apply limit
    calls = query.limit(limit).all()
    
    # Build response (masked numbers)
    items = []
    for call in calls:
        items.append({
            "call_id": call.call_id,
            "channel": call.channel,
            "caller_number": mask_number(call.caller_number),
            "started_at": call.started_at.isoformat(),
            "ended_at": call.ended_at.isoformat() if call.ended_at else None,
            "kb_version": call.kb_version,
            "lang": call.lang,
            "outcome": call.outcome,
            "ai_resolved": call.ai_resolved,
            "turns_count": call.turns_count
        })
    
    return {"items": items}


@router.post("/calls/{call_id}/turns", status_code=201)
def append_turn(
    call_id: str,
    turn_summary: TurnSummary,
    db: Session = Depends(get_db),
    principal: dict = Depends(get_principal)
):
    """Append one TurnSummary (A). Idempotent on (call_id, turn_index)."""
    # Check call exists
    call = db.query(Call).filter(Call.call_id == call_id).first()
    if not call:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Call {call_id} not found"
        )
    
    # Check if turn already exists (idempotency)
    existing = db.query(Turn).filter(
        Turn.call_id == call_id,
        Turn.turn_index == turn_summary.turn_index
    ).first()
    
    if existing:
        # Idempotent: return 200 with existing turn
        return existing.summary_json
    
    # Create new turn
    turn = Turn(
        call_id=call_id,
        turn_index=turn_summary.turn_index,
        summary_json=turn_summary.model_dump(mode="json"),
        created_at=datetime.utcnow()
    )
    db.add(turn)
    
    # Update call turns_count
    call.turns_count = turn_summary.turn_index + 1
    
    db.commit()
    
    # Publish SSE event (after commit)
    sse_hub.publish("call.turn", {
        "call_id": call_id,
        "turn_index": turn_summary.turn_index,
        "path": turn_summary.path,
        "tier": turn_summary.tier,
        "lang": turn_summary.lang
    })
    
    return turn_summary.model_dump(mode="json")


@router.post("/calls/{call_id}/end")
def end_call(
    call_id: str,
    call_end: CallEnd,
    db: Session = Depends(get_db),
    principal: dict = Depends(get_principal)
):
    """End a call (A). Idempotent."""
    call = db.query(Call).filter(Call.call_id == call_id).first()
    if not call:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Call {call_id} not found"
        )
    
    # Check if already ended (idempotency)
    already_ended = call.ended_at is not None
    
    # Update call
    call.ended_at = call_end.ended_at
    call.outcome = call_end.outcome
    call.ai_resolved = call_end.ai_resolved
    call.turns_count = call_end.turns_count
    
    db.commit()
    
    # Publish SSE event only if not already ended (after commit)
    if not already_ended:
        sse_hub.publish("call.ended", {
            "call_id": call_id,
            "ended_at": call_end.ended_at.isoformat(),
            "outcome": call_end.outcome,
            "ai_resolved": call_end.ai_resolved,
            "turns_count": call_end.turns_count
        })
    
    return {"status": "ok"}


@router.get("/calls/{call_id}")
def get_call_detail(
    call_id: str,
    reveal: bool = Query(False),
    db: Session = Depends(get_db),
    principal: dict = Depends(get_principal)
):
    """Get call detail with turns (dashboard). Logs transcript_viewed audit."""
    call = db.query(Call).filter(Call.call_id == call_id).first()
    if not call:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Call {call_id} not found"
        )
    
    # Get turns ordered by turn_index
    turns = db.query(Turn).filter(Turn.call_id == call_id).order_by(Turn.turn_index).all()
    
    # Log audit entry
    actor = principal.get("email", "service")
    write_audit(db, actor, "transcript_viewed", "call", call_id)
    db.commit()
    
    # Mask or reveal caller number
    caller_number = call.caller_number if reveal else mask_number(call.caller_number)
    
    # Audit reveal action
    if reveal and call.caller_number:
        write_audit(db, actor, "number_revealed", "call", call_id, {"field": "caller_number"})
        db.commit()
    
    # Build response
    return {
        "call": {
            "call_id": call.call_id,
            "channel": call.channel,
            "caller_number": caller_number,
            "started_at": call.started_at.isoformat(),
            "ended_at": call.ended_at.isoformat() if call.ended_at else None,
            "kb_version": call.kb_version,
            "lang": call.lang,
            "outcome": call.outcome,
            "ai_resolved": call.ai_resolved,
            "turns_count": call.turns_count
        },
        "turns": [t.summary_json for t in turns]
    }
