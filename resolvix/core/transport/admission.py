"""POST /calls: mint channel + token, enqueue the ConvoAI join, return immediately —
the never-busy admission control (§4.6). Every inbound call is accepted and greeted
before agent readiness is known; if the join queue is full, the call is accepted in
ticket-only mode instead of being refused.
"""
import asyncio
import logging
import random
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from resolvix import settings
from resolvix.core.transport import agora_client
from resolvix.core.transport.token_server import build_token

logger = logging.getLogger("resolvix.admission")
router = APIRouter()

# session_id -> agent_id, so transfer/interrupt/speak/end can reach ConvoAI.
ACTIVE_AGENTS: dict[str, str] = {}
# session_id -> channel, for the reverse lookup transfer_ws needs.
SESSION_CHANNELS: dict[str, str] = {}

_JOIN_QUEUE: asyncio.Queue = asyncio.Queue(maxsize=32)
_WORKERS_STARTED = False


async def _demo_hardcode_answer(agent_id: str, session_id: str) -> None:
    """DEMO SAFETY NET (temporary, DEMO_HARDCODE_MODE-gated): fires a fixed delay
    after join, unconditionally, regardless of anything the caller says or does
    during the window. interrupt() first so this wins over any real pipeline
    response already mid-flight; speak() pushes text straight to TTS, bypassing
    ASR/retrieval/LLM entirely — no dependency on any of those working live.
    One-shot only: nothing here touches session state, so the very next real
    turn goes through the normal graph/shim path unaffected."""
    await asyncio.sleep(settings.DEMO_HARDCODE_DELAY_S)
    try:
        await agora_client.interrupt(agent_id)
    except Exception:
        # Live-confirmed: Agora's /interrupt returns 400 when there's nothing
        # in-flight to interrupt (e.g. caller silent, nothing currently
        # speaking) — best-effort only. Must never block speak() below, since
        # that's the one call this whole feature exists to guarantee.
        logger.warning("DEMO_HARDCODE_MODE: interrupt failed (non-fatal) for session=%s", session_id, exc_info=True)
    try:
        await agora_client.speak(agent_id, settings.DEMO_HARDCODE_TEXT)
        logger.info("DEMO_HARDCODE_MODE: hardcoded answer spoken for session=%s", session_id)
    except Exception:
        logger.exception("DEMO_HARDCODE_MODE: hardcoded speak failed for session=%s", session_id)


async def _join_worker() -> None:
    while True:
        session_id, channel, domain = await _JOIN_QUEUE.get()
        try:
            agent_id = await agora_client.join(channel, domain=domain, session_id=session_id)
            ACTIVE_AGENTS[session_id] = agent_id
            if settings.DEMO_HARDCODE_MODE:
                asyncio.create_task(_demo_hardcode_answer(agent_id, session_id))
        except Exception:
            logger.exception("ConvoAI join failed for session=%s channel=%s", session_id, channel)
        finally:
            _JOIN_QUEUE.task_done()


def _ensure_workers() -> None:
    global _WORKERS_STARTED
    if not _WORKERS_STARTED:
        for _ in range(4):
            asyncio.create_task(_join_worker())
        _WORKERS_STARTED = True


class CallRequest(BaseModel):
    caller_id: str | None = None
    domain: str | None = None


class CallResponse(BaseModel):
    session_id: str
    channel: str
    uid: int
    token: str
    expires_at: int
    ticket_only: bool = False


@router.post("/calls", response_model=CallResponse, status_code=201)
async def create_call(req: CallRequest) -> CallResponse:
    _ensure_workers()
    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    channel = f"call_{session_id}"
    domain = req.domain or settings.DEFAULT_DOMAIN
    caller_uid = random.randint(1, 999)
    token = build_token(channel, caller_uid)
    SESSION_CHANNELS[session_id] = channel

    ticket_only = False
    try:
        _JOIN_QUEUE.put_nowait((session_id, channel, domain))
    except asyncio.QueueFull:
        logger.warning("join queue full — accepting call %s in ticket-only mode", session_id)
        ticket_only = True

    return CallResponse(
        session_id=session_id,
        channel=channel,
        uid=caller_uid,
        token=token.token,
        expires_at=token.expires_at,
        ticket_only=ticket_only,
    )


@router.delete("/calls/{session_id}", status_code=204)
async def end_call(session_id: str) -> None:
    agent_id = ACTIVE_AGENTS.pop(session_id, None)
    SESSION_CHANNELS.pop(session_id, None)
    if agent_id is None:
        raise HTTPException(status_code=404, detail="no active agent for this session")
    await agora_client.leave(agent_id)
