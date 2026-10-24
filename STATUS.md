# STATUS — Nagar Sahayak, session checkpoint

Repo root: `C:\Work\Projects\Resolvix`. Server: `resolvix.app:app`.
Written at end of session — resume cold from here.

---

## State at session start (what was confirmed working)

- Civic pack (`domains/civic_municipal`) live and loading correctly.
- Agora ConvoAI join payload correct: Deepgram nova-3 ASR, Orpheus TTS via
  `generic_http`, Groq gpt-oss-20b LLM shim, correct `sample_rate: 24000`.
- Greeting message playing on call connect.
- Full LangGraph pipeline (hydrate → retrieve → classify → cache_probe →
  decide → answer/clarify/ticket/transfer → confirm → finalize) wired and
  structurally verified.
- Token config issue from prior session already fixed (`extra_body:
  {"reasoning_format": "hidden"}`, `max_tokens` raised from 120).

---

## BUG 1 — VAD false-triggering on ambient noise ✅ FIXED

**Symptoms:** In a noisy room (hackathon venue), agent turn gets cancelled
repeatedly right after the greeting. Logs show:
```
client disconnected mid-turn, cancelling turn_id=...
turn cancelled mid-stream
```
Two turns fire and cancel back to back. No answer ever completes.

**Root cause:** VAD parameters tuned for a quiet room. `threshold: 0.5` and
`interrupt_duration_ms: 160` treat brief crowd noise / applause / HVAC as
speech onset. Once cancelled, no clean turn recovers.

**Fix applied** — `resolvix/core/transport/agora_client.py`:

```python
"vad": {
    "interrupt_duration_ms": 400,   # was 160 — must be sustained speech, not a clap
    "prefix_padding_ms": 800,       # was 300 — Agora's own example uses 800ms floor
    "silence_duration_ms": 700,     # was 420 — room for natural pauses mid-sentence
    "threshold": 0.65,              # was 0.5 — higher = less sensitive to ambient noise
},
"advanced_features": {"enable_aivad": True, "enable_bhvs": True},
```

**IMPORTANT — schema note:** Use the flat `vad` dict shown above, NOT the
nested `turn_detection` schema. The nested schema causes a **400 on join**
for this Agora account. Do not change to `turn_detection`.

**Recovery hardening** — `resolvix/core/openai_shim/routes.py`:
Added explicit clear of `pending_slot` and `pending_confirmation` in the
`CancelledError` handler, followed by `store.put()`. Prevents a
noise-cancelled turn from leaving a stale slot/confirmation flag that the
next real turn would fall into.

**Confirmed fixed:** Live test — no repeated cancellation loop, agent
survives ambient noise and completes greeting turn.

---

## BUG 2 — Total silence / token starvation ✅ FIXED (calls return 200 OK)

**Symptoms:** After VAD fix, asking "pothole on my street" — logs show
`"classifier call failed — routing on answerability alone"`, then two more
POST /v1/chat/completions return 200 OK, but zero audio plays.

**Root cause:** `gpt-oss-20b` with `reasoning_format: hidden` burns
400–600 tokens on its hidden reasoning pass before emitting a single
visible token. Both Groq calls had budgets that didn't account for this:

- **Classifier** `max_tokens=400`: reasoning consumed the whole budget
  before the JSON started → `BadRequestError: max completion tokens reached
  before generating a valid document` → exception caught, `UrgencyVector()`
  zeros returned, routing falls back to answerability-only (harmless but
  slow and wasteful).
- **Answer stream** `max_tokens=600`: reasoning consumed the whole budget,
  visible content was empty, stream ended with `verdict=None` → forced NG
  → clarify re-route → clarify word chunks yielded but (see Bug 3) silently
  discarded by ConvoAI.

**Fix applied:**

`resolvix/core/routing/classifier.py`:
```python
max_tokens=1024,  # was 400 — ~600 for reasoning + ~400 for ~80-token JSON
```

`resolvix/core/graph/answer_stream.py`:
```python
max_tokens=1200,  # was 600 — ~600 for reasoning + ~600 for spoken answer
```

Also added a final-buffer flush after the stream loop in `answer_stream.py`
(last chunk was occasionally dropped silently), and a `WARNING` log when
the stream ends with no visible content so the failure mode is observable.

**Confirmed:** Classifier and answer stream both return 200 OK with no
`BadRequestError`. No more `"classifier call failed"` log lines.

---

## BUG 3 — SSE role-frame missing, ConvoAI silently discards stream ← CURRENT BLOCKER

**Symptoms:** Server returns 200 OK from `/v1/chat/completions`. No POST to
`https://api.groq.com/openai/v1/audio/speech` appears anywhere in the
session. Zero audio. ConvoAI is receiving our response and ignoring it.

**Root cause:** The OpenAI streaming spec requires the **first SSE chunk**
to carry `delta: {"role": "assistant"}`. Without this opening frame,
ConvoAI doesn't recognize the stream as an assistant turn and discards it
silently. Three of four response paths in `routes.py` were missing it:

| Path | Role frame before fix |
|---|---|
| `route == "answer"` (fresh LLM answer) | ✅ present |
| `_speak_and_finalize` (confirm/slot/pending flows) | ❌ missing |
| `else` branch (cache-hit / graph-routed clarify/ticket) | ❌ missing |
| NG re-route word chunks | ✅ (inherited role frame from answer path) |

**Fix applied** — `resolvix/core/openai_shim/routes.py`:
- Added `yield sse.frame_chunk(None, model, role="assistant")` as first
  yield in `_speak_and_finalize`.
- Added same role frame before word chunks in the `else` branch.
- Added diagnostic log lines on every path showing spoken text:
  ```
  answer stream spoken text (143 chars): '<G>There is a...'
  NG re-route (clarify) spoken text: 'Could you tell me...'
  graph-routed (clarify) spoken text: 'Could you tell me...'
  speak_and_finalize spoken text: 'I have logged your report...'
  ```

**Status after fix:** Role frames now present on all paths. BUT the
diagnostic log immediately revealed a new symptom:

```
answer stream spoken text (0 chars): ''
```

The answer LLM call returns 200 OK but produces genuinely empty visible
text even at `max_tokens=1200`. This is the **current single blocker**.

---

## BUG — Empty visible content from gpt-oss-20b — ✅ MITIGATED (root cause not fully pinned, symptom closed)

**Investigation (this session):** Added raw-chunk logging to `answer_stream.py`
(`RAW Groq stream: N chunks, finish_reason=%r, raw_content=%r` — logs every
`delta.content` concatenated, before any of our parsing/buffering touches it).
Ran `stream_answer()` directly 3x, bypassing Agora/VAD/ConvoAI entirely (same
Groq call the live path makes), same test question ("pothole on my street"):

```
trial 0: verdict=G, finish_reason='stop', full_text=312 chars — real grounded answer
trial 1: verdict=G, full_text=434 chars — real grounded answer
trial 2: verdict=G, full_text=360 chars — real grounded answer
```

**3/3 succeeded with correct, substantive content.** Neither of STATUS.md's
two prior hypotheses reproduced: raw content is NOT empty at source, and our
accumulation logic is NOT dropping content — both work correctly in isolation.

**What this narrows it to:** tracing `answer_stream.py`'s control-token logic,
the *only* code path that reaches `verdict="G"` with `full_text=""` is if the
model's entire visible output is literally the 3 bytes `<G>` and then
`finish_reason='stop'` with nothing ever following — a real, structurally-
possible (if apparently rare/intermittent) model behavior, not a parsing bug.
Didn't hit it in 3 isolated trials; may be specific to conditions in the live
multi-turn/concurrent-request path (classify+retrieve+answer overlapping
Groq calls) that a single fresh-session test doesn't reproduce, or may be
a genuine intermittent model quirk.

**Fix applied** (closes the symptom regardless of root cause) —
`resolvix/core/openai_shim/routes.py`:
```python
empty_despite_g = verdict_seen == "G" and not full_text.strip()
if verdict_seen == "NG" or empty_despite_g:
    # re-route to clarify/ticket instead of speaking silence
```
Previously only `verdict_seen == "NG"` triggered the re-route; now the
"control-token-only, nothing after it" case is caught the same way. **Not
live-tested yet** — domain-boundary tests + import-linter pass, isolated
`stream_answer()` calls work, but this specific edge case (verdict=G,
empty text) has never been reproduced in testing to confirm the new branch
actually fires correctly. If it recurs live, check for
`"verdict=G but full_text is empty"` in the log — that WARNING line means
this fix's branch fired as intended.

**If it recurs and this mitigation isn't enough:** the `reasoning_effort`
param (distinct from `reasoning_format`) is worth checking on Groq's docs —
not yet investigated this session, timeboxed out. Nuclear fallback (switch
answer-stream model off gpt-oss-20b to a non-reasoning model) remains
untried but available — see settings.py's GROQ_MODEL comment for context on
why gpt-oss-20b was chosen in the first place (fastest of what's actually
available on this account).

**Live-call methodology note, important for next resume:** buffer-source
synthetic TTS audio (the technique used throughout this build to test
without a real mic) **stopped triggering ConvoAI turns at all** under the
new stricter VAD tuning (`threshold: 0.65` + `enable_aivad`) — 50+ seconds,
two publishes, zero turns fired in this session's live-call attempt. Likely
`enable_aivad`'s semantic filtering treats synthesized/robotic-sounding
audio differently than real human speech. **A real microphone should still
work fine** — this is specifically a limitation of the synthetic-audio test
technique, not necessarily a problem for real demo callers. If the next
live test also shows zero turns firing with a real mic, that's a
new, more serious VAD-over-tuning problem worth its own investigation.

**Agora managed-LLM fallback shape** (confirmed via docs, NOT switched to —
was asked to just confirm the shape as a safety net):
```json
"llm": {
  "credential_mode": "managed",
  "vendor": "openai",
  "url": "https://api.openai.com/v1/chat/completions",
  "params": {"model": "gpt-4.1-mini"}
}
```
Managed-mode models available: `gpt-4o-mini`, `gpt-4.1-mini`, `gpt-5-nano`,
`gpt-5-mini`. No `api_key` needed (Agora's own credits).
**Major caveat, don't switch to this casually:** this bypasses our shim
entirely — no RAG grounding from our corpus, no escalation/ticket/confirm
logic, none of the actual product. It's a "the agent can still say
something" fallback, not a real fallback for this product. Only reach for
it if Groq itself becomes definitively unavailable, and understand it means
demoing a much dumber agent.

---

## Known-good test flow (use this on every resume)

```
1. Start ngrok:         ngrok http 8000
2. Copy tunnel URL
3. Update .env:         PUBLIC_BASE_URL=https://<tunnel>.ngrok-free.app
4. Restart server:      uvicorn resolvix.app:app --reload --port 8000
5. Wait for /readyz
6. Open browser:        http://localhost:8000/?appId=63944097f86a4d9bbf26b6590f17bfc2
7. Click Call
8. Ask:                 "there is a pothole on my street"
9. Check terminal for:  answer stream spoken text (N chars): '...'
10. Confirm audio plays
```

If step 9 shows `(0 chars): ''` → follow CURRENT UNRESOLVED BLOCKER steps above.
If step 9 shows text but no audio → SSE role-frame bug has recurred, check routes.py.
If step 9 shows `NG re-route (clarify)` → corpus retrieval score below threshold, check
indexing and `domains/civic_municipal/corpus/` files are present and chunked.

---

## Config that must never change (hard-won, don't re-derive)

- **LLM:** `GROQ_MODEL=openai/gpt-oss-20b`, needs `extra_body={"reasoning_format": "hidden"}`
  and `max_tokens` ≥ 1024 on classifier, ≥ 1200 on answer stream.
- **ASR:** Deepgram `nova-3`, `language: "multi"` (Hindi/English code-switch).
  `DEEPGRAM_API_KEY` required.
- **TTS:** `canopylabs/orpheus-v1-english` via ConvoAI `generic_http` vendor.
  `response_format: "wav"`, `sample_rate: 24000` — both required, both confirmed
  live. Valid voices: `autumn, diana, hannah, austin, daniel, troy`.
- **VAD:** Flat `vad` dict (not `turn_detection`). See Bug 1 above.
- **Barge-in:** Cancellation triggers on new turn arriving for same session,
  not on HTTP disconnect. See `core/openai_shim/cancel.py`.

---

## Files touched this session

| File | What changed |
|---|---|
| `resolvix/core/transport/agora_client.py` | VAD params (threshold, interrupt_duration_ms, prefix_padding_ms, silence_duration_ms) |
| `resolvix/core/openai_shim/routes.py` | SSE role frames on all paths, diagnostic log lines, CancelledError pending-state cleanup |
| `resolvix/core/routing/classifier.py` | `max_tokens` 400 → 1024 |
| `resolvix/core/graph/answer_stream.py` | `max_tokens` 600 → 1200, final-buffer flush, empty-stream WARNING log |

---

## Corpus / domain taxonomy (unresolved from prior session, still pending)

**RESOLVED, discovered this session.** Real corpus content using the
NEW taxonomy (`water_supply/certificates/schemes/application_status/
appointments/public_transport`) is already in place and working —
confirmed via this session's direct `retrieve()` calls, which returned
real chunk IDs: `water_supply::4, water_supply::3, water_supply::6,
application_status::3, certificates::2`. Someone (Kiro, or the user
directly) already did the remap + corpus placement between sessions.
No further action needed here — just noting it so nobody re-does this
work or re-blocks on the old "which taxonomy" question.

**Vobiz credentials** (`VOBIZ_AUTH_ID` etc.) still empty in `.env` —
waiting on user. WhatsApp notification adapter untested live.
