"""The genuinely-fresh-answer streaming path — deliberately outside the compiled
graph (see build.py's docstring for why). Builds the grounding context from the
same retrieval trace decide() used, streams Groq with the <G>/<NG> control-token
contract (§6.3), and reports the verdict back to the caller so it can re-route on
<NG> without a second LangGraph traversal.
"""
import logging

from groq import AsyncGroq

from resolvix import settings
from resolvix.core.domain.loader import get_pack
from resolvix.core.domain.protocol import TurnContext
from resolvix.core.graph.state import SessionState

logger = logging.getLogger("resolvix.graph.answer_stream")

_groq = AsyncGroq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None


def _build_context(state: SessionState, pack) -> str:
    trace = state.get("last_retrieval")
    if not trace:
        return ""
    parts = []
    for chunk_id in trace["chunk_ids"]:
        chunk = pack.retriever().get_chunk(chunk_id)
        if not chunk:
            continue
        tag = " [SYNTHETIC — hedge this]" if chunk.provenance == "synthetic" else ""
        parts.append(f"### {chunk.heading}{tag}\n{chunk.text}")
    return "\n\n".join(parts)


async def stream_answer(state: SessionState):
    """Yields (verdict, text_piece) tuples. verdict is None until the first piece,
    then fixed for the rest of the stream ('G' or 'NG')."""
    pack = get_pack(state["domain"])
    system_prompt = pack.system_prompt(TurnContext(session_id=state["session_id"], slots=state["slots"], turns=state["turns"]))
    context = _build_context(state, pack)

    if _groq is None:
        yield "NG", ""
        return

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Excerpts:\n{context}\n\nCaller's question: {state['current_utterance']}"},
    ]

    try:
        stream = await _groq.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=1200,  # gpt-oss-20b hidden reasoning consumes 400-600 tokens before the
                              # first visible token. 600 was starving the answer: reasoning ate the
                              # entire budget, visible content was empty, stream ended with
                              # verdict=None → forced NG → clarify re-route → silence because
                              # ConvoAI received an empty assistant turn before the clarify text.
                              # 1200 gives ~600 for reasoning + 600 for a full spoken answer.
            stream=True,
            extra_body={"reasoning_format": "hidden"},
        )
    except Exception:
        logger.exception("answer generation failed, treating as <NG>")
        yield "NG", ""
        return

    verdict = None
    buffer = ""
    raw_chunks = []
    finish_reason = None
    async for chunk in stream:
        delta = chunk.choices[0].delta
        finish_reason = chunk.choices[0].finish_reason or finish_reason
        # RAW, before any of our parsing/buffering/control-token handling touches it.
        raw_chunks.append(delta.content if delta else None)
        if not delta or not delta.content:
            continue
        buffer += delta.content
        if verdict is None:
            if buffer.startswith("<G>"):
                verdict = "G"
                buffer = buffer[3:]
            elif buffer.startswith("<NG>"):
                verdict = "NG"
                buffer = buffer[4:]
            elif len(buffer) < 4:
                continue  # wait for enough bytes to disambiguate <G> vs <NG>
            else:
                # Model didn't emit a control token — assume groundable and treat
                # whatever is buffered as the start of the answer. This handles the
                # case where the model emits a leading space/BOM before the token.
                verdict = "G"
            if buffer:
                yield verdict, buffer
                buffer = ""
        else:
            yield verdict, buffer
            buffer = ""

    raw_joined = "".join(c for c in raw_chunks if c)
    logger.info(
        "RAW Groq stream: %d chunks, finish_reason=%r, raw_content=%r",
        len(raw_chunks), finish_reason, raw_joined,
    )

    # Flush any remainder (e.g. last chunk didn't end on a yield boundary).
    if buffer and verdict is not None:
        yield verdict, buffer
    elif verdict is not None:
        # Control token matched (<G> or <NG>) but the model stopped right there —
        # nothing else ever arrived, so buffer is "" and the loop above never
        # yielded. Still communicate the verdict explicitly rather than silently
        # yielding nothing: live-confirmed bug — raw_content was literally '<NG>'
        # (5 chunks, finish_reason='stop'), stream_answer() yielded ZERO tuples,
        # so the caller's `verdict_seen` stayed None instead of "NG" and fell
        # through to the "successful answer" branch with empty text (a true
        # NG never got routed to clarify/ticket at all — worse than the
        # G-but-empty case, which at least got caught by routes.py's own check).
        yield verdict, ""

    if verdict is None:
        # Stream ended without any visible content — reasoning consumed the entire
        # token budget (confirmed failure mode with gpt-oss-20b at low max_tokens).
        # Yield NG so the shim re-routes to clarify/ticket rather than playing silence.
        logger.warning("answer stream ended with no visible content — token budget exhausted?")
        yield "NG", ""
