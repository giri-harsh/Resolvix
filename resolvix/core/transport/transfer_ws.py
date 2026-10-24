"""Live transfer (Phase 4, §11.2): WS /ws/agents for staff presence + transfer_request
push, POST /calls/{id}/transfer to kick one off, /interrupt and /speak for
server-initiated narration. Muting the AI once a human joins (§5.5's "AI mutes but
stays as scribe") is NOT implemented — that needs either an Agora publish-permission
change or a ConvoAI mute call this pass didn't verify exists; flagged here rather
than silently skipped.
"""
import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from resolvix import settings
from resolvix.core.routing import availability
from resolvix.core.tickets.sqlite_store import SqliteTicketStore
from resolvix.core.transport import agora_client
from resolvix.core.transport.admission import ACTIVE_AGENTS
from resolvix.core.transport.token_server import build_token

logger = logging.getLogger("resolvix.transfer")
router = APIRouter()
_store = SqliteTicketStore()

_STAFF_SOCKETS: set[WebSocket] = set()
_PENDING_CLAIMS: dict[str, asyncio.Event] = {}


@router.websocket("/ws/agents")
async def ws_agents(ws: WebSocket):
    await ws.accept()
    _STAFF_SOCKETS.add(ws)
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("type") == "presence":
                availability.set_available(msg["queue"], msg.get("available", True))
            elif msg.get("type") == "claim":
                session_id = msg.get("session_id")
                event = _PENDING_CLAIMS.get(session_id)
                if event:
                    event.set()
    except WebSocketDisconnect:
        pass
    finally:
        _STAFF_SOCKETS.discard(ws)


async def _broadcast(payload: dict) -> None:
    dead = []
    for ws in _STAFF_SOCKETS:
        try:
            await ws.send_text(json.dumps(payload))
        except Exception:
            dead.append(ws)
    for ws in dead:
        _STAFF_SOCKETS.discard(ws)


class TransferRequest(BaseModel):
    queue: str
    reason: str = ""


@router.post("/calls/{session_id}/transfer", status_code=202)
async def request_transfer(session_id: str, body: TransferRequest):
    if not availability.is_available(body.queue):
        raise HTTPException(status_code=409, detail="no staff available for this queue")

    staff_uid = 2000 + (hash(session_id) % 1000)
    channel = f"call_{session_id}"
    staff_token = build_token(channel, staff_uid)

    event = asyncio.Event()
    _PENDING_CLAIMS[session_id] = event
    await _broadcast({"type": "transfer_request", "session_id": session_id, "queue": body.queue, "reason": body.reason})

    async def _timeout_fallback():
        try:
            await asyncio.wait_for(event.wait(), timeout=settings.TRANSFER_TIMEOUT_MS / 1000)
        except asyncio.TimeoutError:
            logger.info("transfer timed out for session=%s, falling back to ticket", session_id)
            _store.create_ticket(
                domain=settings.DEFAULT_DOMAIN, queue=body.queue, session_id=session_id,
                channel=channel, caller_id=None, caller_attributes={},
                summary=f"Transfer to {body.queue} timed out (no staff answered)",
                transcript=[], intent=body.queue, urgency_vector={}, immediacy=0.9,
                priority=3, route="transfer_failed", sla_due_at=None,
                idempotency_key=f"{session_id}:transfer_failed",
            )
            agent_id = ACTIVE_AGENTS.get(session_id)
            if agent_id:
                try:
                    await agora_client.speak(agent_id, "Nobody's free this second, so I've logged this as priority and you'll get a call back soon.")
                except Exception:
                    logger.exception("speak() failed during transfer-timeout fallback")
        finally:
            _PENDING_CLAIMS.pop(session_id, None)

    asyncio.create_task(_timeout_fallback())

    agent_id = ACTIVE_AGENTS.get(session_id)
    if agent_id:
        try:
            await agora_client.speak(agent_id, "Staying on the line with you — connecting you now.")
        except Exception:
            logger.exception("speak() failed announcing transfer")

    return {"staff_token": staff_token.token, "staff_uid": staff_uid}


@router.post("/calls/{session_id}/interrupt")
async def server_interrupt(session_id: str):
    agent_id = ACTIVE_AGENTS.get(session_id)
    if not agent_id:
        raise HTTPException(status_code=404, detail="no active agent for this session")
    await agora_client.interrupt(agent_id)
    return {"ok": True}


class SpeakRequest(BaseModel):
    text: str


@router.post("/calls/{session_id}/speak")
async def server_speak(session_id: str, body: SpeakRequest):
    agent_id = ACTIVE_AGENTS.get(session_id)
    if not agent_id:
        raise HTTPException(status_code=404, detail="no active agent for this session")
    await agora_client.speak(agent_id, body.text)
    return {"ok": True}
