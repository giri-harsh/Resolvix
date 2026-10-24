"""chat.completion.chunk SSE framing + first-token control-token stripping (§6.3, §11.1)."""
import json
import time

CONTROL_TOKENS = ("<G>", "<NG>")


def frame_chunk(content: str | None, model: str, role: str | None = None, finish_reason: str | None = None) -> str:
    delta = {}
    if role:
        delta["role"] = role
    if content is not None:
        delta["content"] = content
    payload = {
        "id": "chatcmpl-resolvix",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(payload)}\n\n"


DONE = "data: [DONE]\n\n"


def strip_control_token(text: str) -> tuple[str, str | None]:
    """Strip a leading <G>/<NG> verdict token (answer node, §6.3) before it reaches Agora."""
    for tok in CONTROL_TOKENS:
        if text.startswith(tok):
            return text[len(tok):], tok
    return text, None
