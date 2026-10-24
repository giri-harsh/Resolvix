"""Urgency vector extraction — domain-free prompt shell (§6.2). Exemplars, queue
names, and any domain framing are injected by the caller from the active pack;
nothing here names a domain concept.
"""
import json
import logging

from groq import AsyncGroq
from pydantic import BaseModel, Field

from resolvix import settings

logger = logging.getLogger("resolvix.routing.classifier")

_groq = AsyncGroq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None


class UrgencyVector(BaseModel):
    time_criticality: float = 0.0
    blocking: float = 0.0
    harm_if_delayed: float = 0.0
    human_authority_required: float = 0.0
    affect: float = 0.0
    confidence: float = 0.0
    rationale: str = ""
    # answerability is NOT set by the LLM — injected by the answer node (§6.3).


CLASSIFIER_SYSTEM_PROMPT = """You score a caller's utterance on five 0-1 axes and return
strict JSON only, no prose:
{{"time_criticality": 0-1, "blocking": 0-1, "harm_if_delayed": 0-1,
  "human_authority_required": 0-1, "affect": 0-1, "confidence": 0-1,
  "rationale": "<=12 words"}}

time_criticality: does the value of resolving this decay with time?
blocking: is the caller unable to proceed with something right now?
harm_if_delayed: magnitude of safety/financial/legal/academic consequence.
human_authority_required: needs a decision, identity check, money movement, or discretion.
affect: distress in the phrasing (not itself a routing driver, only a tie-breaker).
confidence: your own certainty in this scoring.

{preamble}
Reference examples (utterance -> vector), most similar to the caller's utterance first:
{exemplars}
"""


async def classify(utterance: str, exemplars_text: str, preamble: str = "") -> UrgencyVector:
    if _groq is None:
        logger.warning("classifier unavailable (no GROQ_API_KEY) — caller must route on answerability alone")
        return UrgencyVector()
    try:
        resp = await _groq.chat.completions.create(
            model=settings.GROQ_MODEL,
            temperature=0,
            max_tokens=1024,  # gpt-oss-20b hidden reasoning alone runs 400-600 tokens; 400 was
                              # hitting the limit mid-JSON (confirmed: BadRequestError "max completion
                              # tokens reached before generating a valid document"). 1024 gives the
                              # reasoning pass ~600 tokens and still leaves 400+ for the tiny JSON
                              # output (~80 tokens). The classifier runs concurrently with retrieve/
                              # cache_probe so this doesn't add wall-clock latency to the turn.
            response_format={"type": "json_object"},
            extra_body={"reasoning_format": "hidden"},
            messages=[
                {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT.format(preamble=preamble, exemplars=exemplars_text)},
                {"role": "user", "content": utterance},
            ],
        )
        data = json.loads(resp.choices[0].message.content)
        return UrgencyVector(**data)
    except Exception:
        logger.exception("classifier call failed — routing on answerability alone")
        return UrgencyVector()
