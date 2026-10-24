"""Agora Conversational AI Engine REST client: join/leave only (Phase 0 scope).

Schema below follows Agora's documented join example (system_messages, greeting_message,
max_history, params.model under `llm`; vendor/params under `tts`). Some managed-vendor
defaults are account-specific and unverified without a live Agora project — confirm the
`tts` block against the console on first real call.
"""
import base64
import json
import logging

import httpx

from resolvix import settings

logger = logging.getLogger("resolvix.agora_client")
from resolvix.core.domain.loader import get_pack
from resolvix.core.domain.protocol import TurnContext
from resolvix.core.transport.token_server import build_token

CONVOAI_BASE_URL = "https://api.agora.io/api/conversational-ai-agent/v2/projects"
AGENT_UID = 1000


def _auth_header() -> dict:
    if not settings.AGORA_CUSTOMER_ID or not settings.AGORA_CUSTOMER_SECRET:
        raise RuntimeError("AGORA_CUSTOMER_ID / AGORA_CUSTOMER_SECRET not configured")
    raw = f"{settings.AGORA_CUSTOMER_ID}:{settings.AGORA_CUSTOMER_SECRET}".encode()
    return {"Authorization": f"Basic {base64.b64encode(raw).decode()}"}


def _asr_block(voice) -> dict:
    if settings.USE_AGORA_MANAGED:
        # Managed Deepgram — Agora's own account/credits, not ours. Distinct from
        # vendor "ares" (Agora's separate bundled ASR, live-confirmed dead earlier
        # tonight regardless of language). Same vendor as our proven path, so the
        # keyterm-param fix stays valid; no api_key since Agora covers it.
        return {
            "credential_mode": "managed",
            "vendor": "deepgram",
            "params": {
                "url": settings.DEEPGRAM_URL,
                "model": settings.DEEPGRAM_MODEL,
                "language": voice.asr_language,
            },
        }
    return {
        "vendor": "deepgram",
        "language": voice.asr_language,
        "params": {
            "api_key": settings.DEEPGRAM_API_KEY,
            "url": settings.DEEPGRAM_URL,
            "model": settings.DEEPGRAM_MODEL,
            # keyterm dropped entirely — live-confirmed root cause of every
            # empty transcript this whole session: Agora console showed
            # "model.error_occurred, code: -1000, Failed to start
            # recognition: server rejected WebSocket connection: HTTP 400,
            # vendor: deepgram" on EVERY turn. The comma-joined single-string
            # format guessed here (Deepgram's real API wants repeated
            # `keyterm` params, one per term) was malformed enough that
            # Deepgram rejected the WS handshake outright — not "silently
            # ignored" as assumed, it broke ASR completely. keyterm boost
            # isn't required for the demo; cut rather than reformat under
            # time pressure.
        },
    }


def _llm_block(voice, system_prompt: str, model: str) -> dict:
    if settings.USE_AGORA_MANAGED:
        # KNOWN TRADEOFF, confirmed with the user: this calls OpenAI directly via
        # Agora's managed credits, completely bypassing our /v1/chat/completions
        # shim — no RAG/corpus grounding, no <G>/<NG> control-token routing, no
        # escalation policy, no ticket creation. Persona/greeting still apply
        # (system_messages/greeting_message are passed straight through), but
        # answers are unconstrained general-knowledge, not corpus-grounded.
        return {
            "credential_mode": "managed",
            "vendor": "openai",
            "style": "openai",
            "url": "https://api.openai.com/v1/chat/completions",
            "system_messages": [{"role": "system", "content": system_prompt}],
            "greeting_message": voice.greeting,
            "failure_message": "Sorry, I'm having trouble right now — let me get you to someone.",
            "max_history": 10,
            "params": {"model": settings.AGORA_MANAGED_LLM_MODEL},
        }
    return {
        "url": f"{settings.PUBLIC_BASE_URL}/v1/chat/completions",
        "api_key": settings.AGORA_LLM_SHARED_SECRET,
        "system_messages": [{"role": "system", "content": system_prompt}],
        "greeting_message": voice.greeting,
        "failure_message": "Sorry, I'm having trouble right now — let me get you to someone.",
        "max_history": 10,
        "params": {"model": model},
    }


def _tts_block(voice) -> dict:
    if settings.USE_AGORA_MANAGED:
        # Managed MiniMax TTS — Agora's account/credits, distinct vendor from our
        # Groq/Orpheus path (which is the one leg confirmed 100% working live
        # tonight). Untested end-to-end; only reached when the toggle is on.
        return {
            "credential_mode": "managed",
            "vendor": "minimax",
            "params": {
                "url": "wss://api.minimax.io/ws/v1/t2a_v2",
                "model": "speech-2.6-turbo",
                "voice_setting": {"voice_id": settings.AGORA_MANAGED_TTS_VOICE},
            },
        }
    return {
        "vendor": "generic_http",
        "url": f"{settings.GROQ_TTS_BASE_URL}/audio/speech",
        "headers": {"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
        "params": {
            "model": settings.TTS_MODEL,
            "voice": voice.tts_voice or settings.TTS_VOICE,
            # Orpheus only accepts "wav" — confirmed live via Agora's TTS
            # error log ("response_format must be one of [wav]"); without
            # this, generic_http was sending some other default Groq rejects.
            "response_format": "wav",
            # Fixed the "slowed/pitched-down" playback bug: inspected a real
            # Orpheus WAV response directly (wave module) and confirmed it's
            # genuinely 24000 Hz mono 16-bit, self-describing via its header.
            # generic_http evidently doesn't parse that header and assumes some
            # other rate without this — declaring it explicitly fixes the
            # mismatch (data played at a lower assumed rate sounds slow/low-
            # pitched, which matches the reported symptom exactly).
            "sample_rate": 24000,
        },
    }


async def join(channel: str, domain: str | None = None, session_id: str | None = None) -> str:
    """Fire-and-forget ConvoAI join. Returns the agent_id."""
    domain = domain or settings.DEFAULT_DOMAIN
    pack = get_pack(domain)
    voice = pack.voice_config()
    system_prompt = pack.system_prompt(TurnContext(session_id=session_id or "", slots={}, turns=[]))

    agent_token = build_token(channel, AGENT_UID).token
    model = f"resolvix-{domain}" + (f"-{session_id}" if session_id else "")
    body = {
        "name": f"agent_{channel}",
        "properties": {
            "channel": channel,
            "token": agent_token,
            "agent_rtc_uid": str(AGENT_UID),
            "remote_rtc_uids": ["*"],
            "idle_timeout": 30,
            "asr": _asr_block(voice),
            "llm": _llm_block(voice, system_prompt, model),
            "tts": _tts_block(voice),
            # VAD — flat dict (the `turn_detection` nested schema causes a 400 on
            # join for this Agora account; confirmed live — keep the flat dict).
            #
            # Noisy-venue tuning (hackathon ambient noise fix, confirmed working):
            #
            #   threshold: 0.65  — raised from 0.5.  Higher value requires higher
            #     VAD confidence before declaring speech onset; cuts false triggers
            #     from crowd noise / HVAC / applause.
            #
            #   interrupt_duration_ms: 400  — raised from 160 ms.  Noise must be
            #     sustained 400 ms to register as speech; filters claps/laughs.
            #
            #   prefix_padding_ms: 800  — raised from 300 ms.  Agora's own reference
            #     example uses 800 ms; 300 ms was below their documented floor.
            #
            #   silence_duration_ms: 1200  — raised again from 700ms (was 420
            #     originally). Live-confirmed at 700ms: one continuous sentence was
            #     still splitting into 4+ separate turns within ~1 second (each
            #     firing our own same-session-cancels-prior-turn logic in
            #     cancel.py), meaning 700ms of silence was still being found
            #     somewhere mid-sentence — natural speech pauses (commas, breath)
            #     apparently exceed 700ms more often than expected. 1200ms trades
            #     some perceived turn-taking snappiness for not chopping one
            #     sentence into several broken turns, which reads as much more
            #     "broken" to a live listener than a slightly slower turn-end.
            "vad": {
                "interrupt_duration_ms": 400,
                "prefix_padding_ms": 800,
                "silence_duration_ms": 1200,
                "threshold": 0.65,
            },
            "advanced_features": {"enable_aivad": True, "enable_bhvs": True},
        },
    }
    url = f"{CONVOAI_BASE_URL}/{settings.AGORA_APP_ID}/join"
    logger.info("ConvoAI join payload: %s", json.dumps(_redact(body)))
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=body, headers=_auth_header())
        resp.raise_for_status()
        return resp.json()["agent_id"]


_SECRET_KEYS = {"token", "api_key", "Authorization"}


def _redact(obj):
    """Deep-copy obj with known secret-bearing keys masked, for safe logging."""
    if isinstance(obj, dict):
        return {k: ("<redacted>" if k in _SECRET_KEYS else _redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


async def leave(agent_id: str) -> None:
    url = f"{CONVOAI_BASE_URL}/{settings.AGORA_APP_ID}/agents/{agent_id}/leave"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, headers=_auth_header())
        resp.raise_for_status()


async def interrupt(agent_id: str) -> None:
    """Server-initiated barge-in (§5.4c) — agent interrupts the caller mid-utterance."""
    url = f"{CONVOAI_BASE_URL}/{settings.AGORA_APP_ID}/agents/{agent_id}/interrupt"
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.post(url, headers=_auth_header())
        resp.raise_for_status()


async def speak(agent_id: str, text: str) -> None:
    """Push a line through ConvoAI TTS without an LLM turn (handoff narration, §11.2)."""
    url = f"{CONVOAI_BASE_URL}/{settings.AGORA_APP_ID}/agents/{agent_id}/speak"
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.post(url, json={"text": text}, headers=_auth_header())
        resp.raise_for_status()
