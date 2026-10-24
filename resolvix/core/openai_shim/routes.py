"""POST /v1/chat/completions — the load-bearing endpoint ConvoAI calls every turn (§11.1).

Phase 2+: fans the turn through the LangGraph (hydrate/retrieve/classify/cache_probe
-> decide -> route), then either streams a fresh answer (with the <G>/<NG> re-route,
§6.3) or emits the single-shot text a clarify/transfer/ticket decision produced.
"""
import asyncio
import logging
import re
import time
import uuid

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from resolvix import settings
from resolvix.core.domain.loader import get_pack
from resolvix.core.graph.answer_stream import stream_answer
from resolvix.core.graph.build import get_graph
from resolvix.core.graph.nodes.cache_probe import _cache_for
from resolvix.core.graph.nodes.clarify import clarify as run_clarify
from resolvix.core.graph.nodes.confirm import confirm as run_confirm
from resolvix.core.graph.nodes.finalize import finalize as run_finalize
from resolvix.core.graph.nodes.ticket import ticket as run_ticket
from resolvix.core.graph.nodes.transfer import transfer as run_transfer
from resolvix.core.graph.state import new_session
from resolvix.core.openai_shim import cancel, sse
from resolvix.core.session.store import get_store

logger = logging.getLogger("resolvix.shim")
router = APIRouter()

# model string doubles as the session-correlation channel (PRD Open Question 2's
# documented fallback) since Agora's llm.params passthrough behavior is undocumented.
MODEL_PATTERN = re.compile(r"^resolvix-(?P<domain>[a-zA-Z0-9_]+)(?:-(?P<session_id>sess_[a-zA-Z0-9]+))?$")


def parse_session(body: dict) -> tuple[str, str]:
    if body.get("session_id") and body.get("domain"):
        return body["domain"], body["session_id"]
    model = body.get("model", "")
    m = MODEL_PATTERN.match(model)
    if m:
        domain = m.group("domain")
        session_id = m.group("session_id") or f"sess_{uuid.uuid4().hex[:8]}"
        return domain, session_id
    return settings.DEFAULT_DOMAIN, f"sess_{uuid.uuid4().hex[:8]}"


def _latest_user_text(messages: list[dict]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""


_AFFIRMATIVE_WORDS = {"yes", "yeah", "yep", "correct", "confirm", "haan", "theek", "ok", "okay", "sure", "right", "yup"}
_NEGATIVE_WORDS = {"no", "nahi", "nope", "wrong", "incorrect", "change", "galat"}


def _is_affirmative(text: str) -> bool:
    words = set(re.findall(r"[a-z']+", text.lower()))
    return bool(words & _AFFIRMATIVE_WORDS) and not (words & _NEGATIVE_WORDS)


async def _speak_and_finalize(state, model: str, text: str, turn_start: float):
    """Shared tail for the two confirm-flow short-circuits below — same
    finalize/store/SSE-close sequence the normal graph path uses, just skipping
    the graph itself (pivot v3 §4: re-running retrieve/classify/decide on a
    "yes"/"no" reply makes no sense — same reasoning as the <NG> re-route)."""
    # Role frame first — OpenAI streaming spec requires chunk 0 to establish
    # role:assistant before any content delta. ConvoAI ignores streams that
    # don't open with this frame.
    yield sse.frame_chunk(None, model, role="assistant")
    for word in text.split(" "):
        yield sse.frame_chunk(word + " ", model)
    logger.info("speak_and_finalize spoken text: %r", text)
    state["first_audio_ms"] = round((time.monotonic() - turn_start) * 1000)
    await run_finalize(state)
    get_store().put(state)
    yield sse.frame_chunk(None, model, finish_reason="stop")
    yield sse.DONE


async def _run_turn(state, model: str):
    """Runs the routing graph, then streams/yields the outcome as SSE chunks."""
    turn_start = time.monotonic()
    first_audio_ms = None

    if state.get("pending_slot"):
        slot_key = state["pending_slot"]
        state["slots"] = {**state.get("slots", {}), slot_key: state["current_utterance"].strip()}
        state["pending_slot"] = None
        node_result = await run_confirm(state)
        state.update(node_result)
        async for piece in _speak_and_finalize(state, model, state.get("outcome") or "", turn_start):
            yield piece
        return

    if state.get("pending_confirmation"):
        pending = state["pending_confirmation"]
        state["pending_confirmation"] = None
        if _is_affirmative(state["current_utterance"]):
            node_result = await (run_transfer(state) if pending["route"] == "transfer" else run_ticket(state))
            state.update(node_result)
            text = state.get("outcome") or ""
        else:
            # Simplification, flagged: re-collect the whole thing on "no" rather
            # than re-asking only the wrong slot (pivot PRD §4 wants the latter;
            # cut for time — see the pivot phase notes).
            text = "No problem — what needs to change?"
        async for piece in _speak_and_finalize(state, model, text, turn_start):
            yield piece
        return

    graph = get_graph()
    result = await graph.ainvoke(state)
    route = (result.get("decision") or {}).get("route")

    if route == "answer" and not result.get("cache_hit_answer"):
        yield sse.frame_chunk(None, model, role="assistant")
        pack = get_pack(result["domain"])
        cache = _cache_for(result["domain"])
        full_text = ""
        verdict_seen = None
        async for verdict, piece in stream_answer(result):
            if first_audio_ms is None:
                first_audio_ms = round((time.monotonic() - turn_start) * 1000)
            verdict_seen = verdict
            if verdict == "NG":
                break  # discard the stream, re-route below (§6.3's ~200ms re-route)
            full_text += piece
            if piece:
                yield sse.frame_chunk(piece, model)

        empty_despite_g = verdict_seen == "G" and not full_text.strip()
        if empty_despite_g:
            logger.warning(
                "verdict=G but full_text is empty — model emitted only the control "
                "token and stopped (finish_reason='stop' with nothing after <G>). "
                "Treating as NG rather than speaking silence."
            )
        if verdict_seen == "NG" or empty_despite_g:
            # Re-route without a second graph traversal (see build.py's docstring).
            result["decision"]["vector"]["answerability"] = 0.0
            fallback_route = "clarify" if result.get("clarify_turns", 0) < pack.thresholds().max_clarify else "ticket"
            if fallback_route == "clarify":
                node_result = await run_clarify(result)
            else:
                node_result = await run_ticket(result)
            result.update(node_result)
            result["decision"]["route"] = fallback_route
            text = result["outcome"] or ""
            logger.info("NG re-route (%s) spoken text: %r", fallback_route, text)
            for word in text.split(" "):
                yield sse.frame_chunk(word + " ", model)
        else:
            logger.info("answer stream spoken text (%d chars): %r", len(full_text), full_text[:120])
            cache.store(state["current_utterance"], full_text)
            result["outcome"] = full_text
    else:
        # Cache-hit or non-answer route (clarify/ticket/transfer decided by graph).
        # Role frame required as chunk 0 — same rule as the answer path above.
        first_audio_ms = round((time.monotonic() - turn_start) * 1000)
        text = result.get("outcome") or ""
        logger.info("graph-routed (%s) spoken text: %r", route, text)
        yield sse.frame_chunk(None, model, role="assistant")
        for word in text.split(" "):
            yield sse.frame_chunk(word + " ", model)

    result["first_audio_ms"] = first_audio_ms
    await run_finalize(result)
    get_store().put(result)

    yield sse.frame_chunk(None, model, finish_reason="stop")
    yield sse.DONE


@router.post("/v1/chat/completions")
async def chat_completions(request: Request, authorization: str | None = Header(default=None)):
    expected = f"Bearer {settings.AGORA_LLM_SHARED_SECRET}"
    if not settings.AGORA_LLM_SHARED_SECRET or authorization != expected:
        raise HTTPException(status_code=401, detail="missing or invalid bearer token")

    body = await request.json()
    messages = body.get("messages", [])
    # Diagnostic: current_utterance came back empty 3x live despite the caller
    # genuinely speaking — _latest_user_text() found no role=="user" message at
    # all, meaning ConvoAI's actual request shape differs from what we assumed.
    # Log the raw messages array once to see the real shape before guessing further.
    logger.info("RAW incoming messages array: %r", messages)
    model = body.get("model", f"resolvix-{settings.DEFAULT_DOMAIN}")
    domain, session_id = parse_session(body)
    turn_id = f"{session_id}:{uuid.uuid4().hex[:6]}"

    store = get_store()
    state = store.get(session_id) or new_session(session_id, body.get("channel", ""), domain, body.get("caller_id", "web:anon"))
    state["current_utterance"] = _latest_user_text(messages)
    # The actual Deepgram ASR transcript, exactly as ConvoAI sent it — never logged
    # before this. Live NG/G verdicts depend entirely on this text; without seeing
    # it, "why did this get NG" was unanswerable from our side.
    logger.info("incoming utterance (domain=%s session=%s): %r", domain, session_id, state["current_utterance"])

    if not state["current_utterance"].strip():
        # Live-confirmed real failure mode: ConvoAI's VAD (even after the
        # silence_duration_ms tuning) still occasionally declares a turn on brief
        # noise/mic artifacts with no actual speech — Deepgram returns "", and
        # without this guard we ran the full graph on empty input, producing a
        # confusing, unrelated spoken response (this is what looked like a
        # "garbled clarify template" bug earlier — it was empty-input garbage in,
        # not a template bug). Skip the pipeline entirely: no LLM call, no spoken
        # response, let ConvoAI's own turn-taking continue waiting for real speech.
        logger.warning("empty utterance (domain=%s session=%s) — skipping pipeline, no spoken response", domain, session_id)

        async def _empty_stream():
            yield sse.frame_chunk(None, model, role="assistant")
            yield sse.frame_chunk(None, model, finish_reason="stop")
            yield sse.DONE

        return StreamingResponse(_empty_stream(), media_type="text/event-stream")

    state["turns"] = state.get("turns", []) + [
        {"role": "caller", "text": state["current_utterance"], "ts": time.time(), "interrupted": False, "spoken_prefix": None}
    ]

    async def _stream():
        gen = _run_turn(state, model)
        task = asyncio.current_task()
        # register() cancels any still-running prior turn for this session_id itself —
        # the new turn's arrival is what kills the old one, not a disconnect signal
        # we're waiting to observe (§5.4b; see cancel.py's docstring for why).
        cancel.register(turn_id, task, session_id)
        watcher = asyncio.create_task(cancel.watch_disconnect(request, turn_id))
        try:
            async for piece in gen:
                yield piece
        except asyncio.CancelledError:
            logger.info("turn cancelled mid-stream turn_id=%s", turn_id)
            # VAD false-trigger recovery: a cancelled turn must not leave the session
            # in a half-written state.  _run_turn() only calls store.put() on clean
            # completion, so a cancelled turn never corrupts the store.  What CAN
            # get stranded is an in-flight pending_slot or pending_confirmation that
            # was set during THIS turn before cancellation.  Clear those so the next
            # (real) turn starts from a clean confirm/slot state rather than
            # re-entering a stale confirmation loop from a noise-triggered turn.
            state.pop("pending_slot", None)
            state.pop("pending_confirmation", None)
            # Persist the cleaned state so the next turn sees it.
            try:
                get_store().put(state)
            except Exception:
                pass  # store failure on cancel path is non-fatal
            raise
        finally:
            cancel.unregister(turn_id, session_id)
            watcher.cancel()

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.get("/v1/models")
async def models():
    return {"object": "list", "data": [{"id": f"resolvix-{settings.DEFAULT_DOMAIN}", "object": "model"}]}
