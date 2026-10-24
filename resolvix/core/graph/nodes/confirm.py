"""confirm: read back the filled slots and ask for a yes/no before filing
(pivot PRD §4 — "the single most important new node"). Domain-blind: uses only
pack.identity_fields()/pack.queues(), no hardcoded field names.

Gap discovered building this: the pivot PRD assumes `slots` gets filled somewhere
already ("no state model change, just reuse slots dict") — but nothing in the
existing graph ever extracts slot values from the conversation. Closed here with
a small Groq JSON-mode extraction call, reusing the same model/pattern as the
classifier. This is new, not a port of an existing mechanism — flagged as such.
"""
import json
import logging

from groq import AsyncGroq

from resolvix import settings
from resolvix.core.domain.loader import get_pack
from resolvix.core.graph.nodes._shared import resolve_queue
from resolvix.core.graph.state import SessionState

logger = logging.getLogger("resolvix.graph.confirm")

_groq = AsyncGroq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None


async def _extract_slots(state: SessionState, identity_fields) -> dict:
    if _groq is None or not identity_fields:
        return {}
    transcript = "\n".join(f"{t['role']}: {t['text']}" for t in state.get("turns", []))
    field_list = ", ".join(f'"{f.key}"' for f in identity_fields)
    try:
        resp = await _groq.chat.completions.create(
            model=settings.GROQ_MODEL,
            temperature=0,
            max_tokens=300,
            response_format={"type": "json_object"},
            extra_body={"reasoning_format": "hidden"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Extract these fields if mentioned anywhere in the call transcript: {field_list}. "
                        'Return strict JSON with only the fields you actually found, e.g. {"name": "..."}. '
                        "Omit a key entirely if it was never mentioned. Do not guess."
                    ),
                },
                {"role": "user", "content": transcript},
            ],
        )
        data = json.loads(resp.choices[0].message.content)
        return {k: v for k, v in data.items() if isinstance(v, str) and v.strip()}
    except Exception:
        logger.exception("slot extraction failed — proceeding with whatever slots are already known")
        return {}


def _build_confirmation_text(pack, queue_label: str, slots: dict) -> str:
    # Field key, not the full bilingual slot prompt — "name Rajesh Kumar, phone
    # 98765..." reads as natural speech; "aapka naam / your name: Rajesh Kumar"
    # reads like a form label being read aloud.
    details = ", ".join(f"{f.key} {slots[f.key]}" for f in pack.identity_fields() if slots.get(f.key))
    return pack.confirm_prompt(queue_label, details)


async def confirm(state: SessionState) -> dict:
    pack = get_pack(state["domain"])
    identity_fields = pack.identity_fields()

    extracted = await _extract_slots(state, identity_fields)
    slots = {**state.get("slots", {}), **extracted}

    missing = [f for f in identity_fields if f.required and not slots.get(f.key)]
    if missing:
        field = missing[0]
        return {"slots": slots, "pending_slot": field.key, "outcome": f"And {field.prompt}?"}

    decision = state.get("decision") or {}
    queue_key = resolve_queue(state, pack)
    queue = pack.queues().get(queue_key)
    queue_label = queue.label if queue else queue_key

    text = _build_confirmation_text(pack, queue_label, slots)
    return {
        "slots": slots,
        "pending_slot": None,
        "pending_confirmation": {"route": decision.get("route", "ticket"), "queue": queue_key},
        "outcome": text,
    }
