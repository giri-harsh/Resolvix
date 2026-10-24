"""PSTN ingress (Phase 5, optional — §4.5). TwiML greeting + µ-law<->PCM16 resampling
are real; the actual Agora-side publish/subscribe is NOT implemented.

Why: bridging raw PCM into an Agora RTC channel from a server process needs Agora's
native Real-Time SDK (or the Linux Server SDK the PRD names) — there is no official,
free, pure-Python package for this. Reaching for an unofficial binding or vendoring a
native SDK wasn't something I could verify as zero-cost within this pass, so rather
than fake a working bridge, the seam is marked below. The TwiML endpoint and the
resampling math are real and independently testable.
"""
import audioop
import base64
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from resolvix import settings
from resolvix.core.domain.loader import get_pack

logger = logging.getLogger("resolvix.pstn")
router = APIRouter()


@router.post("/pstn/twilio/voice")
async def twilio_voice():
    pack = get_pack(settings.DEFAULT_DOMAIN)
    greeting = pack.voice_config().greeting
    stream_url = settings.PUBLIC_BASE_URL.replace("http://", "ws://").replace("https://", "wss://") + "/pstn/twilio/stream"
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say>{greeting}</Say>
  <Connect>
    <Stream url="{stream_url}" />
  </Connect>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


def ulaw_8k_to_pcm16_16k(ulaw_bytes: bytes) -> bytes:
    """Twilio's 8kHz mu-law -> 16kHz PCM16, the format ConvoAI/Agora expect."""
    pcm16_8k = audioop.ulaw2lin(ulaw_bytes, 2)
    pcm16_16k, _ = audioop.ratecv(pcm16_8k, 2, 1, 8000, 16000, None)
    return pcm16_16k


def pcm16_16k_to_ulaw_8k(pcm16_bytes: bytes) -> bytes:
    pcm16_8k, _ = audioop.ratecv(pcm16_bytes, 2, 1, 16000, 8000, None)
    return audioop.lin2ulaw(pcm16_8k, 2)


@router.websocket("/pstn/twilio/stream")
async def twilio_stream(ws: WebSocket):
    await ws.accept()
    logger.warning("PSTN bridge: resampling only, no Agora publish/subscribe wired — see module docstring")
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("event") == "media":
                ulaw_bytes = base64.b64decode(msg["media"]["payload"])
                pcm16_16k = ulaw_8k_to_pcm16_16k(ulaw_bytes)
                # TODO: publish pcm16_16k into the Agora RTC channel for this call.
                # Requires the Agora Linux Server SDK (native), not wired this pass.
                _ = pcm16_16k
    except WebSocketDisconnect:
        pass
