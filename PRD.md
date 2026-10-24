# Resolvix — Product Requirements Document

**Version:** 2.0 (rebuild)
**Status:** Draft for build
**Owner:** Harshit Giri
**Date:** 2026-08-19
**Supersedes:** v1 IVR implementation (`Resolvix/main.py` Twilio TwiML flow)

---

## 1. Current State Audit

Read: `README.md`, `Resolvix/README.md`, `Resolvix/main.py` (414 L), `Resolvix/rag.py` (225 L), `Resolvix/ticket_store.py` (224 L), `Resolvix/docs/*.md` (6 files, 322 L), `Resolvix/DATA_SOURCES.md`, `Resolvix/.env.example`, both HTML frontends, `data/` (crawl + 2 notebooks + 2 scripts).

1. **What exists:** a working single-process FastAPI app implementing a turn-based Twilio IVR campus helpdesk for AKGEC — DTMF category menu, one speech capture per turn, TF-IDF retrieval, Groq-phrased grounded answer, SQLite ticket, WhatsApp ping.
2. **Architecture:** synchronous request/response webhooks. Twilio `Gather`/`Say` drives every turn; `main.py` is a state machine over 8 TwiML endpoints with state in a process-local `SESSIONS: dict[str, dict]` keyed by `CallSid` (`main.py:50`).
3. **Retrieval:** `DocIndex` (`rag.py:108`) — `TfidfVectorizer` with a hand-rolled 9-suffix stemmer (`rag.py:32-46`), chunked on `##`, category-scoped to exactly one file via `CATEGORY_FILES` (`rag.py:48`). Built once at import; no persistence, no embeddings.
4. **Confidence:** two gates — a TF-IDF score floor (`RAG_CONFIDENCE_THRESHOLD=0.18`) and an LLM `NOT_ANSWERABLE` sentinel check (`rag.py:221`). The README correctly argues gate 2 is the real relevance filter; gate 1 is only a candidate pre-filter.
5. **Urgency:** `detect_urgency()` (`ticket_store.py:43`) is a 12-entry substring keyword match returning `"high" | "normal"`. It is the entire routing signal today, and there is no live-transfer path at all — every escalation becomes a ticket.
6. **Domain coupling is pervasive, not layered.** Digit-to-category maps are duplicated in `rag.py:48,57` and `ticket_store.py:19,28`; `roll_no` is a first-class column in the `tickets` table (`ticket_store.py:54-64`); IVR prompt copy, `COLLEGE_NAME`, `Polly.Aditi`, and `en-IN` are inline in `main.py`.
7. **Defects found:** both HTML files hardcode `API_BASE = 'http://localhost:8001'` while both READMEs instruct `--port 8000`; the root README embeds `./Resolvix/assets/resolvix-demo.gif` but the only asset is `assets/1.gif`; `.gitignore` ignores `.env.example`, so the documented setup file is untracked; `datetime.utcnow()` (`ticket_store.py:96,182`) is deprecated.
8. **Corpus:** 6 markdown docs, ~5,700 words, honestly provenance-audited in `DATA_SOURCES.md` — but **hostel, exam-policy and several service sections are `SYNTHETIC`**, covering 3 of 6 categories. `data/rag_cleaned_2.json` is documented as corrupt.

**Survives the rebuild:** `docs/*.md` corpus (relocated verbatim); `_chunk_markdown()`'s HTML-comment stripping + boilerplate/heading-only chunk dropping (`rag.py:75-105`) — earned logic, keep it; the `NOT_ANSWERABLE` second-opinion *concept* (re-shaped into a structured answerability score); the SQLite store + in-place `PRAGMA table_info` migration pattern; `/api/tickets`, `PATCH /api/tickets/{id}/status`, `/api/insights`; `campus-helpdesk-department.html`; `DATA_SOURCES.md`; `data/web-markdown.py` + `akg_links.txt` (corpus regeneration).

**Deleted:** all 8 TwiML endpoints and the entire `twilio.twiml` dependency; the DTMF menu and its digit-to-category maps in all four places; the `SESSIONS` dict; `CLARIFY_Q1/Q2` fixed-script clarification; `detect_urgency()`'s keyword list; `RAG_CONFIDENCE_THRESHOLD`; `POST /api/query` (turn-based contract); `campus-helpdesk-prototype.html` (a click-through mock of a flow that no longer exists); `data/markdown-csv.py`, `data/rag_cleaned_2.json`, `raw_data.txt`, `fit_data.txt`.

---

## 2. Problem Statement & Vision

**Problem.** The v1 IVR solves the retrieval problem and fails the *conversation* problem. A caller with a real problem does not know whether it is a "fees" problem or an "exams" problem, cannot say so in one utterance, and cannot interrupt. Each turn costs a full Twilio `Gather` round trip (2–4 s of dead air), the caller must sit through a six-option menu before speaking, and the only exit from a failed answer is a ticket — so a student locked out of a hostel at 11 p.m. gets a callback promise.

**Vision.** Resolvix is a voice agent that *answers a helpline*. The caller hears a human-paced greeting within a second of connecting, describes the problem in their own words, is interrupted-and-interruptible, and gets one of three outcomes inside the same continuous audio session: a grounded answer, a warm transfer to a human already in the same audio channel, or a structured ticket with a callback commitment. The domain — what "the knowledge base" and "a human" mean — is a directory of configuration, not code.

**Positioning in one sentence:** a helpline that never sounds like a phone tree, never sounds busy, and knows the difference between a question and an emergency.

---

## 3. Goals / Non-Goals

### Goals

| ID | Goal | Measure of done |
|---|---|---|
| G1 | Full-duplex natural voice conversation over Agora | No DTMF anywhere; caller can interrupt agent mid-word and agent stops within 200 ms |
| G2 | Sub-second perceived response | p50 end-of-speech to first agent audio <= 900 ms; p95 <= 1.4 s |
| G3 | Grounded answering as the default path | >= 60 % of the demo query suite answered from corpus without escalation |
| G4 | Two-route escalation, inferred not keyed | Live transfer and ticket both demonstrable; routing driven by a scored classifier, zero keyword rules in the routing layer |
| G5 | Domain swap without touching core | Adding a second domain pack produces an empty `git diff --stat core/`; enforced in CI by `import-linter` |
| G6 | Zero marginal cost | Full 10-minute demo runs on free tiers only; no card on file for any service except Twilio's optional trial |
| G7 | Never busy | Every inbound call is accepted and greeted before agent readiness is known |
| G8 | LangGraph reachable as an OpenAI LLM | `POST /v1/chat/completions` passes Agora ConvoAI's LLM validation and streams SSE deltas |

### Non-Goals

- **Multi-tenant SaaS.** One domain pack active per process. Multi-tenancy would be a routing key on the shim; deliberately deferred.
- **Answer-accuracy maximisation.** Explicitly traded away for latency (§9). No rerankers, no multi-hop retrieval, no self-consistency voting.
- **Production concurrency engineering.** No autoscaling, no load balancer, no Redis cluster, no worker-pool tuning. The accept-then-route queue (§4.6) is roughly 40 lines.
- **Real telephony scale.** PSTN ingress is a demo bridge on a Twilio trial number, not a carrier integration.
- **Dashboard authentication, RBAC, audit trail.** Known gap carried forward from v1; tracked as R9.
- **Multilingual operation.** Hindi is a config value (`domain.yaml: asr.language`), not a tested path.
- **Replacing the synthetic corpus sections.** Content sourcing is out of engineering scope; the *guardrail* that marks them is in scope (§10.3).

---

## 4. System Architecture

### 4.1 Component diagram

```
                     +------------------------- CALLER SIDE -------------------------+
                     |                                                              |
  +------------+     |  +--------------------+        +--------------------------+   |
  |   PSTN     |     |  | Web caller page    |        | PSTN bridge (optional)   |   |
  |   phone    |--------| agora-rtc-sdk-ng   |        | Twilio <Stream> over WS  |   |
  +------------+ TwiML|  | (browser, free)    |        | mu-law 8k <-> PCM 16k    |   |
                     |  +---------+----------+        | agora_rtc_sdk (server)   |   |
                     |            |                   +------------+-------------+   |
                     +------------|--------------------------------|-----------------+
                                  |          AUDIO (RTC)           |
                                  v                                v
              ==================================================================
              ||        AGORA RTC CHANNEL      channel = call_<uuid>          ||
              ||  uid 1..999 caller | uid 1000 AI agent | uid 2000+ human     ||
              ==================================================================
                          |                                   |
        +-----------------+------------------+                | human joins the
        | AGORA CONVERSATIONAL AI ENGINE     |                | SAME channel on
        | (managed, in-media-path)           |                | transfer - no
        |  * VAD + barge-in                  |                | conference bridge
        |  * ASR  (streaming)                |                |
        |  * TTS  (streaming)                |                v
        |  * turn / interrupt state          |     +------------------------+
        +-----------------+------------------+     | Human agent console    |
                          |                        | department.html +      |
      OpenAI-compatible   | HTTPS + SSE            | Agora Web SDK          |
      /v1/chat/completions|                        +-----------+------------+
                          v                                    | WS /ws/agents
  ====================================================================================
  ||                    RESOLVIX BACKEND   (FastAPI, Python 3.11)                   ||
  ||                                                                                ||
  ||  +--------------------------------------------------------------------------+  ||
  ||  | core/openai_shim   POST /v1/chat/completions -> SSE chat.completion.chunk|  ||
  ||  |   * auth: Bearer == AGORA_LLM_SHARED_SECRET                              |  ||
  ||  |   * reads session_id / channel / domain from llm.params passthrough       |  ||
  ||  |   * one asyncio Task per turn; client disconnect => task.cancel()         |  ||
  ||  +---------------------------------+----------------------------------------+  ||
  ||                                    v                                           ||
  ||  +------------------------- core/graph (LangGraph) ------------------------+   ||
  ||  |                                                                         |   ||
  ||  |  hydrate --> +-- retrieve -------+ --> decide --> +- answer --> stream   |   ||
  ||  |              |  hybrid BM25+dense|                +- clarify --> stream  |   ||
  ||  |              +-- classify -------+                +- transfer -> tool    |   ||
  ||  |              |  urgency axes     |                +- ticket ----> tool   |   ||
  ||  |              +-- cache_probe ----+       ^                               |   ||
  ||  |                 (three in parallel)      +-- deadline guard 1800 ms      |   ||
  ||  +------+---------------+---------------+---------------+-------------------+   ||
  ||         v               v               v               v                       ||
  ||  +------------+  +------------+  +------------+  +----------------+             ||
  ||  | retrieval  |  | routing    |  | tickets    |  | transport      |             ||
  ||  | index +    |  | policy +   |  | TicketStore|  | AgoraClient    |             ||
  ||  | sem. cache |  | calibration|  | (SQLite)   |  | token server   |             ||
  ||  +-----+------+  +-----+------+  +-----+------+  +--------+-------+             ||
  ====================================================================================
            |               |               |                  |  REST, Basic auth
            v               v               v                  v  (customer id:secret)
  +-------------------------------------------------+  +-----------------------------+
  | domains/<pack>/  <- THE ONLY SWAPPABLE THING    |  | Agora ConvoAI REST          |
  |  corpus/*.md   domain.yaml   prompts/           |  |  POST .../agents/join       |
  |  tools.py   escalation.yaml   exemplars.yaml    |  |  POST .../agents/{id}/leave |
  +------------------------+------------------------+  |  POST .../agents/{id}/speak |
                           |                           |  POST .../{id}/interrupt   |
                           v                           +-----------------------------+
  +------------------+  +------------------+  +---------------------------------------+
  | Groq             |  | Groq / Azure     |  | resolvix.db (SQLite)                  |
  | llama-3.1-8b     |  | playai-tts / F0  |  | tickets  sessions  calibration        |
  | (inference)      |  | (TTS fallback)   |  | query_log                             |
  +------------------+  +------------------+  +---------------------------------------+
```

### 4.2 Audio path (never touches Python in the happy case)

Caller mic → Agora RTC → ConvoAI ASR → **text** → our shim → **text** → ConvoAI TTS → Agora RTC → caller ear.

This is the load-bearing architectural decision: **Resolvix never handles PCM in the answering path.** Audio stays inside Agora's in-network pipeline, so the ASR→LLM and LLM→TTS hops are colocated with the media rather than routed through our free-tier host. The only place we touch raw audio is the optional PSTN bridge (§4.5), which is off the critical path for the web-caller demo.

**Alternative considered:** own the audio — subscribe to the channel with the Agora Linux Server SDK, run Groq `whisper-large-v3-turbo` for STT and Groq `playai-tts` for TTS ourselves. *Rejected:* adds two extra internet round trips (channel → our host → Groq → our host → channel) worth roughly 400–600 ms, and re-implements the VAD/barge-in that ConvoAI already ships. Retained as the documented fallback if the ConvoAI trial is exhausted (§8.3).

### 4.3 Data path

Agora ConvoAI calls our OpenAI-compatible endpoint once per turn with the recent message history (bounded by `llm.params.max_history`). Because that history is *Agora's* view of the conversation, it is not authoritative:

- Agora's history holds **utterances**; Resolvix's `SessionState` holds **decisions** — urgency-vector history, retrieval traces, filled slots, the escalation ratchet, deadline spend.
- Correlation is via `llm.params` passthrough: Agora forwards extra keys under `llm.params` verbatim into the request body, so the agent is provisioned at join time with `params: {"model": "...", "session_id": "...", "channel": "...", "domain": "campus_akgec", "caller_id": "..."}` and every turn arrives self-identifying. No cookies, no header hacks.
- **Tool calls never cross the wire to Agora.** ConvoAI expects assistant text. The graph executes retrieval, ticket creation and transfer in-process and streams only the spoken result. Consequence: the shim must be the *whole* agent, not a proxy.

### 4.4 Agora configuration requirements

| Credential | Where used | Notes |
|---|---|---|
| `AGORA_APP_ID` | Web SDK client, token builder, ConvoAI REST path | Public; safe in the browser |
| `AGORA_APP_CERTIFICATE` | Token server only | **Must be enabled** in the Agora console. Server-side secret. Without it, tokens are null-auth and the channel is world-joinable |
| `AGORA_CUSTOMER_ID` / `AGORA_CUSTOMER_SECRET` | ConvoAI REST Basic auth | `Authorization: Basic base64(id:secret)`. RESTful API key pair, distinct from the App Certificate |
| `AGORA_LLM_SHARED_SECRET` | Sent as `llm.api_key` at join; verified by our shim | Stops anyone from spending our Groq quota through a public `/v1/chat/completions` |

**Token server** (`core/transport/token_server.py`, `agora-token-builder`): `POST /rtc/token {channel, uid, role}` → `RtcTokenBuilder.buildTokenWithUid(app_id, app_cert, channel, uid, role, expire_ts)`. TTL 3600 s, `role=PUBLISHER` for both caller and human agent. UID convention: caller `random(1..999)`, AI agent `1000` (fixed, so `remote_rtc_uids` filtering and dashboard presence detection are deterministic), human agents `2000 + staff_id`.

### 4.5 PSTN ingress (optional, Phase 5)

`POST /pstn/twilio/voice` returns TwiML that immediately speaks the greeting (so the caller hears something inside 500 ms even if channel setup lags) and then opens `<Connect><Stream>` to `WS /pstn/twilio/stream`. The bridge resamples Twilio's 8 kHz µ-law to/from 16 kHz PCM16 and publishes/subscribes on the Agora channel via the Agora Linux Server SDK. This is the only Python in the audio path; budget +150 ms each way and expect degraded ASR at 8 kHz (R6).

### 4.6 Never-busy admission control

`POST /calls` creates the channel, mints the caller token, and returns **immediately**; the ConvoAI join is fire-and-forget onto a bounded `asyncio.Queue(maxsize=32)` drained by four workers. If the agent has not joined within `AGENT_JOIN_GRACE_MS=1500` the caller has already heard the cached greeting and the first turn simply starts late; if the queue is full, the call is accepted in **ticket-only mode** (greeting plus "describe the issue and we'll log it and call you back"). That is the entire feature: two states, one queue, no scaling story.

---

## 5. Conversational Flow Specification

### 5.1 Turn lifecycle

```
T0  caller stops speaking
T1  ConvoAI VAD declares end-of-turn            (silence_duration_ms)
T2  final ASR transcript emitted
T3  POST /v1/chat/completions reaches the shim  (stream=true)
T4  graph fans out:  retrieve || classify || cache_probe
T5  decide() picks one of {answer, clarify, transfer, ticket}
T6  first SSE delta leaves the shim             <- the latency gate, §9
T7  ConvoAI TTS emits its first audio frame
T8  caller hears the first syllable
```

### 5.2 Opening

The greeting is **not generated**. `domain.yaml: greeting` is passed to ConvoAI as `llm.params.greeting_message`, which the engine speaks from its own TTS pipeline the instant the agent joins — zero LLM involvement, and therefore zero risk of a cold-start stall at the most latency-visible moment of the whole call.

> Campus pack: *"A K G E C helpdesk, this is the automated assistant. What can I help you with?"*

Open-ended by design. No menu, no enumerated options: enumerating options is what makes an IVR an IVR, and it trains the caller to speak in category labels instead of describing the actual problem.

### 5.3 Underspecification and clarification

The graph asks a clarifying question when retrieval is ambiguous **across intents** (the top two candidate chunks come from different `queue`s) or when a domain tool declares a required slot missing.

- **At most two clarifying turns per issue**, then force a decision. v1's fixed `CLARIFY_Q1/Q2` script is deleted; the question is generated from the ambiguity itself (`prompts/clarify.md`, templated with the competing candidates) so it is always answerable in one breath — *"Is that about paying the hostel fee, or getting the security deposit back?"*, not *"Could you tell me a bit more detail?"*
- Clarification is **cheap and eager**; escalation is the fallback. A caller answering a targeted question is a caller who is not on hold.
- Slot capture replaces v1's `/collect-name` + `/collect-roll` DTMF entry. Identity fields are collected conversationally *only when a tool needs them*, and `domain.yaml: identity_fields` declares which they are — the campus pack asks for name and roll number, a clinic pack would ask name and date of birth, with no code change.

### 5.4 Barge-in and interruption

Three distinct interruption cases, three mechanisms.

**(a) Caller interrupts the agent** — handled inside ConvoAI:

```yaml
vad:
  interrupt_duration_ms: 160     # sustained speech before it counts as a real interrupt
  prefix_padding_ms: 300         # audio kept before the trigger so the first word isn't clipped
  silence_duration_ms: 420       # end-of-turn detection; lower = snappier, higher = fewer false cuts
  threshold: 0.5
advanced_features:
  enable_aivad: true             # semantic VAD: tells "mm-hm" backchannel from a real interrupt
  enable_bhvs: true              # background human voice suppression; helpline callers are rarely somewhere quiet
```

`interrupt_duration_ms: 160` is a deliberate tuning: below ~120 ms a cough cuts the agent off, above ~250 ms the agent talks over the caller long enough to feel rude. `enable_aivad` is what makes an acknowledgement ("okay… yeah…") *not* an interruption — the single highest-value setting for perceived naturalness.

**(b) Our in-flight generation must abort.** When ConvoAI cancels a turn it closes the SSE connection. The shim runs each turn as a named `asyncio.Task`; the disconnect triggers `task.cancel()`, which propagates through the LangGraph `astream` and aborts the Groq request. Requirements:

- Every node is cancellation-safe: no partial writes outside a transaction.
- **Tool side effects must be idempotent.** A ticket-creating tool cancelled after its INSERT but before the spoken confirmation must not create a second ticket on the retry turn. Every tool call carries `idempotency_key = sha256(session_id + tool + canonical_args)` enforced by a `UNIQUE` index (§10.2). This is the sharpest correctness hazard barge-in introduces.
- The interrupted partial utterance is recorded as `turns[-1].interrupted = true` along with the token prefix already spoken, so the next turn resumes instead of restarting the sentence.

**(c) Agent interrupts the caller** — rare and intentional: a caller monologuing past `MAX_CALLER_TURN_MS=25000`, or a high-urgency classification landing mid-utterance that warrants an immediate "I'm getting someone on the line right now." Implemented server-side via `POST /projects/{app_id}/agents/{agent_id}/interrupt` followed by `/speak`.

### 5.5 Terminal states

| Outcome | Spoken commitment | System action |
|---|---|---|
| Answered | Answer, then "anything else?" — one open question, never a keypad prompt | `query_log(answered=1)` |
| Clarify exhausted | "I don't want to guess at that — let me get you to someone." | Falls into transfer or ticket per §6 |
| Live transfer | "Staying on the line with you — connecting you now." The agent narrates the wait; silence during a transfer reads as a dropped call | Human joins the channel; AI mutes but stays as scribe |
| Transfer failed (no human inside `TRANSFER_TIMEOUT_MS=20000`) | "Nobody's free this second, so I've logged this as priority and you'll get a call back within *N*." | Ticket with `priority` bumped one level, `route='transfer_failed'` |
| Ticket | "Logged as ticket 4 B 2 1 — someone will call you back on this number." | Ticket plus destination notify |
| Idle / hang-up | — | `idle_timeout: 30` on the agent; session finalised, transcript persisted |

Ticket IDs are spoken digit-by-digit with spaces — v1 already did this (`main.py:268`); keep it, it survives a bad line.

---

## 6. Escalation Decision Engine

### 6.1 Design principle

The routing decision is a **scored decision surface over continuous signals**, not a rule table. Rules require someone to enumerate the cases for every new domain; a scored surface requires someone to state a *tolerance* — how much worse is a needless transfer than a missed one — which is a single economic judgment per domain, expressible in six numbers.

`core/routing/` contains **no domain vocabulary of any kind**. v1's `URGENCY_KEYWORDS` list (`ticket_store.py:37-40`) is deleted outright, and a unit test asserts no lexical constant tables are reintroduced there.

### 6.2 The urgency vector

One Groq call, `llama-3.1-8b-instant`, `temperature=0`, `max_tokens=120`, `response_format={"type": "json_object"}`, run **concurrently** with retrieval:

```python
class UrgencyVector(BaseModel):
    time_criticality: float          # 0-1  does the value of resolution decay with time?
    blocking: float                  # 0-1  is the caller unable to proceed with something right now?
    harm_if_delayed: float           # 0-1  magnitude of safety / financial / legal / academic consequence
    human_authority_required: float  # 0-1  needs a decision, identity check, money movement, or discretion
    affect: float                    # 0-1  distress in the phrasing
    answerability: float             # 0-1  NOT from the LLM - injected, see 6.3
    confidence: float                # 0-1  the classifier's own certainty
    rationale: str                   # <= 12 words, for the dashboard and the audit trail
```

`affect` is deliberately **not** a routing driver on its own — an angry caller asking about warranty length still gets an answer. It acts as a tie-breaker inside the clarify band and as a dashboard signal for staff coaching.

### 6.3 Answerability without an extra round trip

v1 spent a second LLM call on the `NOT_ANSWERABLE` sentinel. That call was the right idea and the wrong cost. Reshaped:

```
answerability = 0.35 * normalize(hybrid_retrieval_score) + 0.65 * grounding_verdict
```

`grounding_verdict` comes from the **first token of the answer generation itself**. The answer prompt requires the model to emit exactly one control token before any prose: `<G>` (the excerpts answer this) or `<NG>` (they do not). Because it is the first token, the verdict is known at time-to-first-token — no extra request, no serialized wait — and the control token is stripped in the SSE transform before anything reaches Agora. On `<NG>` the stream is discarded and the graph re-routes, having spent only ~200 ms.

**Trade-off:** the answer model now double-duties as the relevance judge, so a mis-emitted control token both wastes the generation and misroutes. Accepted: the alternative is a serialized second call that costs 200–300 ms on *every* turn, which violates §9.

### 6.4 Policy function

```python
# core/routing/policy.py  - domain-free; every constant loaded from escalation.yaml
need_human = max(v.human_authority_required, 1.0 - v.answerability)
immediacy  = 0.50*v.time_criticality + 0.30*v.blocking + 0.20*v.harm_if_delayed

if v.answerability >= t.answer_floor and immediacy < t.immediacy_hi:   route = ANSWER
elif need_human >= t.human_floor and immediacy >= t.immediacy_hi:      route = TRANSFER
elif need_human >= t.human_floor:                                      route = TICKET
elif clarify_turns < t.max_clarify:                                    route = CLARIFY
else:                                                                  route = TICKET
```

Campus-pack defaults: `answer_floor: 0.55`, `human_floor: 0.50`, `immediacy_hi: 0.62`, `max_clarify: 2`.

### 6.5 What makes it dynamically adjusting

**(1) Retrieved rubric anchors, not static few-shots.** `exemplars.yaml` holds labelled utterances with hand-assigned vectors. At classify time the four nearest by embedding are retrieved (same index infrastructure as the corpus, separate namespace) and inlined as anchors in the prompt. Consequences: the rubric sharpens as the exemplar set grows; onboarding a new domain means *writing exemplars*, not tuning code; and the anchors are always topically adjacent to the live utterance, which is worth more than four generic ones.

**(2) Online threshold calibration from human feedback.** Every escalation is labellable from the dashboard:

```
POST /api/tickets/{id}/feedback
{ "verdict": "correct" | "should_have_transferred" | "should_have_ticketed" | "should_have_been_answered" }
```

Each label is stored in `calibration_events` alongside the frozen vector that produced the decision. Once `N >= 20` labels exist for a domain, `core/routing/calibration.py` grid-searches the three thresholds to minimise an asymmetric cost:

```
cost = c_false_transfer*FT + c_missed_transfer*MT + c_wrong_answer*WA + c_needless_ticket*NT
```

with the four costs declared in `escalation.yaml`. A campus helpdesk sets `c_false_transfer` high (staff time is the scarce resource); a clinic line sets `c_missed_transfer` an order of magnitude higher (a missed urgent call is unacceptable) and will consequently over-transfer — correctly. Grid search over three scalars on a few hundred stored vectors is milliseconds, needs no training infrastructure, and every threshold move is explainable as "these 20 labels moved `immediacy_hi` from 0.62 to 0.58."

**Alternative considered:** fine-tune a small classifier on the labels. *Rejected:* no free training budget, no labelled volume at demo scale, and it destroys the explainability that makes the threshold move defensible to the staff who supplied the labels.

**(3) Availability gating — the world, not the classifier.** `human_availability(queue)` is a runtime input to the policy, not an axis of the vector. If no staff are on-shift for the target queue, `TRANSFER` is unreachable and collapses to `TICKET` with `priority + 1` and a different spoken line. This keeps the classifier honest: it scores the *situation*; the policy accounts for *reality*.

### 6.6 Stability guarantees

- **Immediacy ratchet.** `immediacy_t := max(immediacy_t, immediacy_{t-1})` within a session. A caller who has established an emergency is never de-escalated by a subsequently calm sentence. `answerability` is explicitly *not* ratcheted — it is per-question.
- **Hysteresis on upgrade.** Moving from `ANSWER` to `TRANSFER` requires either `confidence >= 0.75` on a single turn or the same recommendation on two consecutive turns. Without this the route oscillates mid-sentence and the caller hears the agent change its mind.
- **Classifier timeout is not a blocker.** Hard deadline 200 ms. On breach, route on `answerability` alone: groundable → answer, otherwise → ticket. The call never waits on the classifier. This is §9's principle applied literally.

### 6.7 Worked examples

Same policy, same code, three domains. Nothing below is hardcoded — these are traces.

| Utterance | Domain | time | block | harm | authority | answerability | immediacy / need_human | Route |
|---|---|---|---|---|---|---|---|---|
| "My appliance isn't working and I need it right now" | product support | 0.9 | 0.9 | 0.5 | 0.7 | 0.3 | 0.82 / 0.70 | **TRANSFER** |
| "What's the warranty period?" | product support | 0.1 | 0.1 | 0.0 | 0.0 | 0.9 | 0.08 / 0.10 | **ANSWER** |
| "I'd like to schedule a product demo" | product support | 0.2 | 0.1 | 0.0 | 0.9 | 0.4 | 0.13 / 0.90 | **TICKET** |
| "The hostel gate is locked and I'm outside" | campus | 0.95 | 1.0 | 0.6 | 0.8 | 0.2 | 0.89 / 0.80 | **TRANSFER** |
| "When is the fee deadline?" | campus | 0.3 | 0.2 | 0.2 | 0.0 | 0.92 | 0.25 / 0.08 | **ANSWER** |
| "I need a bonafide certificate for a visa" | campus | 0.4 | 0.3 | 0.2 | 0.85 | 0.7 | 0.33 / 0.85 | **TICKET** |
| "I think I'm having chest pain" | clinic | 1.0 | 1.0 | 1.0 | 1.0 | 0.1 | 1.00 / 1.00 | **TRANSFER** |

The clinic row also shows why `c_missed_transfer` belongs in config: with campus thresholds a borderline clinical case could land in the clarify band, and one extra clarifying question is the wrong behaviour on a medical line. The pack lowers `immediacy_hi` to 0.35 and `max_clarify` to 1. Routing code unchanged.

---

## 7. Domain Abstraction Layer

### 7.1 The boundary, stated as a rule

> **Nothing under `core/` may name a domain concept.** No "fee", no "hostel", no "student", no "roll number", no category enum, no queue name, no phone number, no prompt copy. Core knows about *turns, routes, queues-as-opaque-strings, slots-as-declared-schemas, and destinations-as-URIs*. Everything that gives those meaning lives in `domains/<pack>/`.

Changing the entire use case is: swap the corpus, the tool definitions, the system prompt, and the escalation destinations. Four edits, one directory, zero core diff.

### 7.2 Module layout

```
resolvix/
├── app.py                          # composition root: reads RESOLVIX_DOMAIN, builds everything
├── core/                           # ============ FIXED ============
│   ├── transport/
│   │   ├── agora_client.py         # ConvoAI REST: join/leave/speak/interrupt/history
│   │   ├── token_server.py         # RtcTokenBuilder wrapper
│   │   ├── admission.py            # accept-then-route queue (§4.6)
│   │   └── pstn_bridge.py          # Twilio Media Streams <-> Agora RTC (optional)
│   ├── openai_shim/
│   │   ├── routes.py               # POST /v1/chat/completions, GET /v1/models
│   │   ├── sse.py                  # chat.completion.chunk framing, control-token stripping
│   │   └── cancel.py               # per-turn Task registry, disconnect -> cancel
│   ├── graph/
│   │   ├── build.py                # StateGraph assembly; nodes are domain-blind
│   │   ├── state.py                # SessionState TypedDict (§10.1)
│   │   └── nodes/                  # hydrate, retrieve, classify, cache_probe, decide,
│   │                               #   answer, clarify, transfer, ticket, finalize
│   ├── routing/
│   │   ├── classifier.py           # UrgencyVector extraction; prompt shell only
│   │   ├── policy.py               # the decision surface (§6.4)
│   │   ├── calibration.py          # threshold grid search from feedback labels
│   │   └── availability.py         # on-shift lookup, transfer reachability
│   ├── retrieval/
│   │   ├── protocol.py             # Retriever Protocol
│   │   ├── hybrid_index.py         # BM25 + dense + RRF, built from a corpus dir
│   │   ├── chunking.py             # PORTED from rag.py:75-105 (comment strip, boilerplate drop)
│   │   └── semantic_cache.py       # embedding-keyed answer cache
│   ├── tickets/
│   │   ├── protocol.py             # TicketStore Protocol
│   │   └── sqlite_store.py         # PORTED from ticket_store.py, domain fields removed
│   ├── notify/
│   │   ├── protocol.py             # Destination Protocol
│   │   └── adapters/               # whatsapp.py, webhook.py, email.py, console.py
│   ├── session/store.py            # SessionStore: in-proc dict + SQLite spill
│   ├── domain/
│   │   ├── protocol.py             # THE CONTRACT: DomainPack (§7.3)
│   │   └── loader.py               # discovers + validates a pack at boot
│   └── telemetry/spans.py          # per-stage timing, latency budget enforcement
│
├── domains/                        # ========== SWAPPABLE ==========
│   ├── campus_akgec/               # the working example
│   │   ├── domain.yaml             # identity, greeting, voice, asr lang, queues, identity_fields
│   │   ├── escalation.yaml         # thresholds, cost weights, destinations per queue
│   │   ├── exemplars.yaml          # labelled utterances -> urgency vectors (rubric anchors)
│   │   ├── prompts/
│   │   │   ├── system.md           # the agent persona and grounding contract
│   │   │   ├── clarify.md          # ambiguity -> question template
│   │   │   └── classify_preamble.md# optional domain framing for the classifier
│   │   ├── corpus/                 # <- docs/*.md moved here verbatim
│   │   │   ├── fee_structure.md      hostel_rules.md     exam_schedule.md
│   │   │   └── admissions.md         placements.md       application_forms.md
│   │   ├── tools.py                # @tool functions; the only domain Python
│   │   └── PROVENANCE.md           # <- DATA_SOURCES.md moved here
│   └── clinic_demo/                # proves the boundary in Phase 6
│       └── (same six files, ~200 lines of yaml + 40 lines of tools.py)
│
├── web/
│   ├── caller.html                 # Agora Web SDK caller page (NEW)
│   └── department.html             # <- campus-helpdesk-department.html, + transfer button
├── tests/
│   └── test_domain_boundary.py     # asserts core/ imports nothing from domains/
├── importlinter.ini                # CI-enforced layer contract
└── research/                       # <- data/ notebooks and crawler, out of the runtime path
```

### 7.3 The contract

```python
# core/domain/protocol.py
class DomainPack(Protocol):
    name: str
    def system_prompt(self, ctx: TurnContext) -> str: ...
    def clarify_prompt(self, candidates: list[Chunk]) -> str: ...
    def tools(self) -> list[BaseTool]: ...              # LangChain @tool objects
    def retriever(self) -> Retriever: ...              # built from corpus/ at boot
    def exemplars(self) -> list[LabelledUtterance]: ...
    def thresholds(self) -> Thresholds: ...
    def costs(self) -> CostWeights: ...
    def queues(self) -> dict[str, Queue]: ...          # opaque id -> {label, destinations, sla_minutes}
    def identity_fields(self) -> list[SlotSpec]: ...   # what a ticket needs from the caller
    def voice_config(self) -> VoiceConfig: ...         # greeting, tts voice id, asr language
```

`domains/campus_akgec/domain.yaml`, abridged:

```yaml
name: campus_akgec
display_name: "A K G E C student helpdesk"
greeting: "A K G E C helpdesk, this is the automated assistant. What can I help you with?"
voice:
  asr_language: en-IN            # v1's VOICE_LANG, now config
  tts_voice: Fritz-PlayAI        # Groq playai-tts voice id
  tts_fallback_voice: en-IN-NeerjaNeural   # Azure F0
identity_fields:
  - {key: name,    prompt: "your full name",    required: true}
  - {key: roll_no, prompt: "your roll number",  required: true, pattern: "^[0-9]{7,12}$"}
queues:
  fees:        {label: Fees,        sla_minutes: 240,  destinations: [whatsapp:+91XXXXXXXXXX]}
  hostel:      {label: Hostel,      sla_minutes: 60,   destinations: [whatsapp:+91XXXXXXXXXX], transferable: true}
  exams:       {label: Exams,       sla_minutes: 240,  destinations: [whatsapp:+91XXXXXXXXXX]}
  admissions:  {label: Admissions,  sla_minutes: 480,  destinations: [whatsapp:+91XXXXXXXXXX]}
  placements:  {label: Placements,  sla_minutes: 480,  destinations: [whatsapp:+91XXXXXXXXXX]}
  general:     {label: General,     sla_minutes: 480,  destinations: [console:]}
```

Note what *disappeared*: the digit keys. v1's `"1" | "2" | ... | "6"` existed only because DTMF needed them, and they were duplicated across four dictionaries in two modules. Queues are now named strings resolved by the retriever's `queue` front-matter field, and there is exactly one definition.

### 7.4 Fixed vs swappable

| Concern | Fixed (core) | Swappable (pack) |
|---|---|---|
| Agora channel, tokens, agent lifecycle | ✅ | — |
| VAD / barge-in tuning | ✅ defaults | pack may override `vad` block |
| OpenAI shim, SSE framing, cancellation | ✅ | — |
| Graph topology and node implementations | ✅ | — |
| Urgency axes and their meaning | ✅ | — |
| Threshold values and cost weights | — | ✅ `escalation.yaml` |
| Rubric anchors | — | ✅ `exemplars.yaml` |
| Retrieval algorithm (BM25 + dense + RRF) | ✅ | — |
| Corpus content and chunk front-matter | — | ✅ `corpus/` |
| Tool set | invocation machinery ✅ | definitions ✅ `tools.py` |
| Ticket table core columns | ✅ | caller attributes ✅ (JSON) |
| Escalation destinations | adapter interface ✅ | targets ✅ `escalation.yaml` |
| Prompts and persona | ✅ shell | ✅ `prompts/` |

### 7.5 Enforcement, not convention

An architectural rule nobody checks is a comment. Three checks, all in CI:

1. `importlinter.ini` — a **layers** contract: `domains` may import `core`; `core` may never import `domains`. `lint-imports` fails the build on violation.
2. `tests/test_domain_boundary.py` — loads both packs and asserts the graph builds, routes, and produces distinct behaviour with byte-identical `core/`.
3. `make prove-swappable` — the demo-able proof for Phase 6: `RESOLVIX_DOMAIN=clinic_demo` boots and answers a clinical query, then `git diff --stat core/` prints nothing.

---

## 8. Tech Stack & Free-Tier Dependency Table

### 8.1 Stack

| Layer | Choice | Identifier / version | One-line justification |
|---|---|---|---|
| Transport | Agora RTC | `agora-rtc-sdk-ng` 4.x (web), `agora-token-builder` 1.0.0 | Mandated; also the only transport where a human joins the caller's existing audio session with no bridge |
| Voice pipeline | Agora Conversational AI Engine | REST `v2` | ASR + VAD + barge-in + TTS in the media path — the latency win we cannot reproduce ourselves |
| Orchestration | LangGraph | `langgraph` >= 0.2, `langchain-core` >= 0.3 | Explicit state machine with per-node cancellation; the graph *is* the flow spec in §5 |
| LLM serving contract | FastAPI OpenAI shim | `fastapi` 0.115, `sse-starlette` | ConvoAI speaks OpenAI; anything else needs a proxy we would have to maintain |
| Inference | Groq | `llama-3.1-8b-instant` (answers, classifier), `llama-3.3-70b-versatile` (offline eval only) | Fastest free TTFT available; 8B is sufficient because answers are extractive from retrieved chunks |
| STT | Agora built-in ASR (primary) / Groq `whisper-large-v3-turbo` (bridge + fallback) | — | Agora's is in-path; Groq Whisper is only reachable if we own the audio, which costs 400 ms (§4.2) |
| TTS | Groq `playai-tts` via OpenAI-compatible `/v1/audio/speech` (primary) / Azure Speech `F0` (fallback) | voice `Fritz-PlayAI` / `en-IN-NeerjaNeural` | Mandated free-tier first; Azure is the fallback because it is a *native* ConvoAI vendor. **See A3 — Groq TTS is not a first-class ConvoAI vendor** |
| Embeddings | `fastembed` + `BAAI/bge-small-en-v1.5` | ONNX, CPU, ~130 MB | Local, no API call in the hot path, ~10 ms/query; a hosted embedding API would add a round trip |
| Lexical retrieval | `rank_bm25` (BM25Okapi) + v1's stemmer | — | Replaces TF-IDF cosine; better on short queries, still zero-dependency |
| Store | SQLite + WAL | stdlib `sqlite3` | Carried from v1 for the same reason v1 chose it: nothing external can fail live |
| Session state | in-process dict, SQLite spill; Upstash Redis optional | `upstash-redis` | Single process by design (Non-Goals); the spill exists so a restart mid-demo does not lose tickets |
| Config | `pydantic-settings` + `PyYAML` | — | Pack validation at boot beats a runtime `KeyError` inside a live call |
| Hosting | local + `ngrok` (dev), Fly.io / Render free (demo) | — | ConvoAI needs a public HTTPS LLM URL |
| Observability | structured JSON logs + `/metrics`; per-stage spans | `structlog` | Latency is the product; unmeasured latency is unmanaged |

**Removed from v1's stack:** `twilio.twiml.voice_response` (all of it), `scikit-learn`, `numpy` as a direct dependency. `twilio` stays only if PSTN ingress (Phase 5) or WhatsApp notify is enabled.

### 8.2 Free-tier dependency table

| Service | Free allowance | What we use it for | Behaviour at the limit |
|---|---|---|---|
| **Agora RTC** | 10,000 voice minutes / month (audio) | Every call channel | Calls fail to join. Mitigation: a second Agora project on a second email doubles it; demo calls are ~3 min so 10k min is ~3,300 calls |
| **Agora ConvoAI Engine** | Time-limited free trial, then per-agent-minute billing (**not covered by the 10k RTC minutes**) | ASR, VAD, TTS, turn management | **The single biggest budget risk (R1).** Fallback: self-hosted pipeline (§4.2) using Agora Linux Server SDK + Groq Whisper + Groq TTS, at +400–600 ms |
| **Groq** (`llama-3.1-8b-instant`) | Free dev tier; ~30 RPM / ~14,400 RPD / token-per-minute cap (verify at `console.groq.com/settings/limits`) | Answer generation, urgency classifier | HTTP 429 with `retry-after`. Ladder: (1) serve from semantic cache, (2) drop the classifier and route on answerability alone, (3) switch `GROQ_MODEL` to a less-contended model, (4) fall back to extractive answering — return the retrieved chunk body with no LLM at all, which v1 already does (`rag.py:159-161`) |
| **Groq** (`whisper-large-v3-turbo`) | Free dev tier; per-hour and per-day audio-second caps | STT only in the self-hosted fallback path | 429. Fallback: Deepgram $200 signup credit, or Azure Speech F0 |
| **Groq** (`playai-tts`) | Free dev tier; **notably low request-per-day cap relative to a call volume** | Primary TTS | 429 mid-call is unacceptable. Pre-emptive design: cache the greeting and all fixed lines as WAV at build time; switch to Azure on the first 429 and stay switched for the process lifetime |
| **Azure Speech** | F0 tier: 0.5 M characters / month neural TTS, 5 audio-hours/month STT | TTS fallback; native ConvoAI vendor (`vendor: microsoft`) | Silence. Next: ElevenLabs free (10k chars/mo) or Cartesia free tier |
| **Twilio** | Trial credit (~$15) + one number; trial calls restricted to verified numbers | PSTN ingress (Phase 5), WhatsApp notify | Credit exhausted → PSTN demo unavailable; web caller page unaffected. Alternative: SignalWire or Plivo trial |
| **Twilio WhatsApp Sandbox** | Free; recipients must join the sandbox with a keyword; 24-hour session window | Ticket notify to staff | Message rejected outside the window. Fallback: `webhook:` adapter to a Discord/Slack incoming webhook (unlimited, free) — already an adapter in `core/notify/adapters/` |
| **ngrok** | Free: 1 online tunnel, random URL per restart, 20k requests/mo | Local dev webhook exposure | New URL on restart → re-provision the agent's `llm.url`. Handled: `make dev` re-reads the tunnel URL and re-joins |
| **Fly.io / Render** | Fly: limited free allowance; Render: free web service that sleeps after 15 min idle | Hosting the shim | Render cold start (~30 s) breaks the first call. Mitigation: a cron ping every 10 min, or use Fly |
| **Upstash Redis** | 10,000 commands / day, 256 MB | Optional session store | Falls back to in-process dict + SQLite spill; no code path change (both behind `SessionStore`) |
| **SQLite / fastembed / rank_bm25** | Unlimited, local | Store, embeddings, lexical retrieval | No limit; disk only |
| **GitHub Pages** | Unlimited public static | `caller.html`, `department.html` | None |

### 8.3 Degradation ladder (ordered; each step is survivable on a live call)

1. Semantic cache hit → no LLM call at all.
2. Classifier unavailable → route on `answerability` alone.
3. Answer LLM unavailable → extractive answer: speak the retrieved chunk body verbatim (v1's existing no-Groq fallback).
4. Retrieval empty or degraded → skip straight to escalation; do not stall.
5. TTS vendor 429 → switch vendor for the process lifetime, log once.
6. ConvoAI unavailable → self-hosted audio pipeline, accept +500 ms.
7. Everything degraded → accept the call, greet from the cached WAV, take a ticket. **The line still answers.**

---

## 9. Latency Budget & Performance Targets

### 9.1 Design principle, stated with its consequences

> **Latency is prioritised over answer accuracy.** A fast partial answer plus an escalation beats a slow perfect one.

This is not a slogan; it is enforced as five specific behaviours:

1. **Every stage has a hard deadline, and every deadline has a defined breach action.** No stage is allowed to simply take longer.
2. **No serialized reranking, no multi-hop retrieval, no self-consistency.** Single retrieval pass, single generation pass.
3. **Answerability is inferred from the first generated token** (§6.3) rather than a preceding call.
4. **A breach is spoken, not hidden.** At `TOTAL_ANSWER_DEADLINE_MS=1800` with no tokens produced, the graph abandons the answer path, streams "Let me get you to someone who can answer that properly," and routes to escalation. A caller who waits three seconds and then gets a good answer has had a worse call than one who waited one second and got a human.
5. **Accuracy regressions are accepted and measured, not argued about.** The eval suite reports answer accuracy alongside p95 latency; a change that improves accuracy while pushing p95 past target is rejected.

### 9.2 Per-stage budget (end of caller speech → first agent audio)

| # | Stage | Owner | p50 | p95 | Hard deadline | Breach action |
|---|---|---|---|---|---|---|
| 1 | VAD end-of-turn | Agora | 420 ms | 420 ms | `silence_duration_ms` | — (tuning knob, not a failure) |
| 2 | Final ASR transcript | Agora | 90 ms | 180 ms | — | Partial transcript used |
| 3 | Agora → shim network | Internet | 40 ms | 90 ms | — | — |
| 4 | Session hydrate | core | 5 ms | 15 ms | 50 ms | Start a fresh session |
| 5 | **retrieve ∥ classify ∥ cache_probe** | core | **110 ms** | **190 ms** | 250 ms | Use whatever completed; classify may be dropped |
| 5a | · semantic cache probe | core | 12 ms | 25 ms | 40 ms | Miss |
| 5b | · hybrid retrieval (BM25 + dense + RRF) | core | 45 ms | 95 ms | 150 ms | Lexical-only results |
| 5c | · urgency classifier (Groq 8B, JSON) | Groq | 105 ms | 185 ms | 200 ms | Route on answerability alone |
| 6 | decide() | core | < 1 ms | 2 ms | — | — |
| 7 | LLM time-to-first-token | Groq | 190 ms | 320 ms | 600 ms | Abandon answer → escalate |
| 8 | Shim → Agora first delta | Internet | 40 ms | 90 ms | — | — |
| 9 | TTS first audio frame | Agora/vendor | 180 ms | 330 ms | 500 ms | Vendor switch (persistent) |
| 10 | RTC delivery to caller | Agora | 60 ms | 120 ms | — | — |
| | **Total, excluding VAD** | | **~715 ms** | **~1,240 ms** | **1,800 ms** | Escalate |
| | **Total, as the caller experiences it** | | **~1,135 ms** | **~1,660 ms** | — | — |

Targets: **p50 ≤ 900 ms and p95 ≤ 1.4 s excluding VAD**; the VAD 420 ms is a perception tuning knob traded against false end-of-turn cuts. Add **+150 ms each direction** on the PSTN path (Phase 5), which is why the web caller page is the demo default.

### 9.3 Other targets

| Metric | Target | Why |
|---|---|---|
| Barge-in stop latency | ≤ 200 ms from caller onset to agent audio ceasing | Above ~300 ms the agent feels like it is ignoring you |
| Greeting latency | ≤ 800 ms from channel join | Pre-rendered, no LLM (§5.2) |
| Call accept latency (`POST /calls`) | ≤ 150 ms p99 | The never-busy guarantee (§4.6) |
| Semantic cache hit rate | ≥ 35 % after 200 calls | Helpline traffic is dominated by ~40 repeated questions — v1's README makes exactly this observation |
| Cache-hit response | ≤ 350 ms total | No LLM in the path |
| Transfer connect | ≤ 8 s from decision to human audible | Beyond ~10 s callers assume the call dropped |
| Tool execution (ticket create) | ≤ 80 ms | Local SQLite; notify is fire-and-forget |

### 9.4 Instrumentation

Every stage emits a span into `core/telemetry`; each turn logs one JSON line with all ten timings plus `route`, `answerability`, `immediacy`, `cache_hit`, `deadline_breaches[]`. `GET /metrics` exposes histograms. The eval harness (`make bench`) replays a fixed 40-utterance transcript suite through the graph with a stubbed transport and prints the p50/p95 table above — so a latency regression fails a build rather than surfacing in a demo.

---

## 10. Data Models

### 10.1 Session state (LangGraph state object)

```python
# core/graph/state.py
class Turn(TypedDict):
    role: Literal["caller", "agent"]
    text: str
    ts: float
    interrupted: bool          # set when barge-in truncated an agent turn
    spoken_prefix: str | None   # what the caller actually heard before the cut

class RetrievalTrace(TypedDict):
    chunk_ids: list[str]
    scores: list[float]
    queues: list[str]
    lexical_ms: int
    dense_ms: int

class EscalationDecision(TypedDict):
    route: Literal["answer", "clarify", "transfer", "ticket"]
    vector: dict[str, float]    # frozen UrgencyVector for calibration replay
    immediacy: float
    need_human: float
    thresholds_version: str     # which calibration generation produced this
    rationale: str
    human_available: bool

class SessionState(TypedDict):
    session_id: str             # our id; the join-time correlation key
    channel: str                # Agora channel name, call_<uuid>
    agent_id: str | None        # returned by ConvoAI /join
    caller_uid: int
    caller_id: str              # E.164, or "web:<anon>"
    domain: str                 # pack name; NOT a category
    language: str
    started_at: float
    turns: list[Turn]
    slots: dict[str, str]       # filled identity_fields
    pending_slot: str | None
    clarify_turns: int
    last_retrieval: RetrievalTrace | None
    urgency_history: list[dict]
    immediacy_ratchet: float    # monotonic, §6.6
    decision: EscalationDecision | None
    tool_calls: list[dict]      # {tool, args, idempotency_key, result, ms}
    deadline_spend_ms: int
    breaches: list[str]
    outcome: str | None
```

Persistence: authoritative copy in `SessionStore` (in-process dict), spilled to `sessions` (SQLite) on every route decision and at finalisation — so a crash loses in-flight audio but never a ticket. LangGraph checkpointing is deliberately *not* used for cross-turn durability; a turn is short enough that the checkpointer's write cost is pure latency.

### 10.2 Ticket schema

```sql
CREATE TABLE tickets (
  id                TEXT PRIMARY KEY,        -- 8 hex upper, spoken digit-by-digit
  created_at        TEXT NOT NULL,           -- datetime.now(timezone.utc).isoformat()
  updated_at        TEXT NOT NULL,
  domain            TEXT NOT NULL,           -- pack name
  queue             TEXT NOT NULL,           -- opaque queue id from domain.yaml
  session_id        TEXT NOT NULL,
  channel           TEXT,
  caller_id         TEXT,                    -- E.164 or web:<anon>
  caller_attributes TEXT NOT NULL DEFAULT '{}',  -- JSON; roll_no/name/dob live HERE, not as columns
  summary           TEXT NOT NULL,           -- agent-written, one sentence
  transcript        TEXT NOT NULL,           -- full turn list, JSON
  intent            TEXT,                    -- best-effort label for analytics
  urgency_vector    TEXT NOT NULL,           -- JSON, frozen at decision time
  immediacy         REAL NOT NULL,
  priority          INTEGER NOT NULL,        -- 0 low .. 3 critical, derived from immediacy
  route             TEXT NOT NULL,           -- 'ticket' | 'transfer_failed' | 'post_transfer'
  status            TEXT NOT NULL DEFAULT 'open',   -- open | in_progress | resolved | closed
  sla_due_at        TEXT,                    -- created_at + queue.sla_minutes
  assigned_to       TEXT,
  resolution        TEXT,
  idempotency_key   TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_tickets_idem ON tickets(idempotency_key);   -- barge-in safety, §5.4b
CREATE INDEX ix_tickets_queue_status ON tickets(queue, status, priority DESC, created_at DESC);

CREATE TABLE calibration_events (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at     TEXT NOT NULL,
  domain         TEXT NOT NULL,
  ticket_id      TEXT,
  session_id     TEXT NOT NULL,
  vector         TEXT NOT NULL,   -- the frozen UrgencyVector
  actual_route   TEXT NOT NULL,
  verdict        TEXT NOT NULL,   -- correct | should_have_transferred | should_have_ticketed | should_have_been_answered
  labelled_by    TEXT
);

CREATE TABLE thresholds (        -- calibration output; versioned, never overwritten
  version     TEXT PRIMARY KEY,  -- e.g. campus_akgec@g7
  domain      TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  values      TEXT NOT NULL,     -- JSON
  n_labels    INTEGER NOT NULL,
  cost        REAL NOT NULL,
  active      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE query_log (         -- carried from v1, domain fields generalised
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL, domain TEXT, queue TEXT, query TEXT,
  answered   INTEGER, route TEXT, answerability REAL, immediacy REAL,
  cache_hit  INTEGER, first_audio_ms INTEGER
);
```

Migration from v1's table: `category` ("1".."6") → `queue` (named string) via a one-time map; `roll_no` and `name` columns → `caller_attributes` JSON; `phone` → `caller_id`; `query` → `summary` + `transcript`; `urgency` ("high"/"normal") → `immediacy` (0.85/0.35) + `priority`. Same `PRAGMA table_info` guarded-ALTER pattern v1 already uses (`ticket_store.py:68-70`), so existing `tickets.db` files upgrade in place.

### 10.3 RAG corpus format

Existing docs keep their `##`-per-chunk structure and their HTML-comment provenance markers. Added: YAML front matter per file, which is what makes retrieval queue-aware without a digit map.

```markdown
---
doc_id: fee_structure
title: Fee Structure and Payment
queue: fees                 # resolves to domain.yaml queues.fees
language: en
source_urls:
  - https://akgec.ac.in/fee-structure-for-new-students2026-27
retrieved_at: 2026-08-01
provenance: mixed           # sourced | synthetic | mixed
speak_currency_as: words    # "Rs. 1,42,156" -> "one lakh forty-two thousand..."
---

# AKGEC — Fee Structure & Payment FAQ

## B.Tech First Year Academic Fee
<!-- provenance: sourced -->
<!-- answer_hint: First-year B.Tech academic fee for 2026-27 is one lakh forty-two thousand one hundred fifty-six rupees. -->
The academic fee for B.Tech students admitted in the 2026-27 session is Rs. 1,42,156 ...

## Late Payment and Instalments
<!-- provenance: synthetic -->
...
```

Three additions and why each earns its place:

- **`queue`** — replaces the `CATEGORY_FILES` digit map. Retrieval returns the queue with the chunk, so escalation destination selection is a property of *the retrieved knowledge*, not of a keypress.
- **`answer_hint`** — a pre-written, spoken-form one-sentence answer, seeded into the semantic cache at index time. This is how the top ~40 questions hit the ≤ 350 ms path with no LLM call. Optional per section.
- **`provenance: synthetic`** — chunks so marked are retrievable but **the answer node must hedge them**: the system prompt requires "I believe X, but let me confirm that with the office" phrasing, and `escalation.yaml: synthetic_answerability_penalty: 0.25` subtracts from answerability so synthetic content escalates sooner. `DATA_SOURCES.md` documents that 3 of 6 categories are partly synthetic; speaking those as settled fact to a real student is the highest-consequence failure this system can have, so the corpus format encodes the hedge rather than relying on a human remembering.

Index build: `make build-index` walks `corpus/`, applies `chunking.py` (ported from `rag.py:75-105`), computes BM25 statistics and bge-small vectors, and writes `corpus.index.npz` + `corpus.lock.json` (per-chunk sha256). Boot loads the artefact — no embedding work inside a call. A corpus edit without a rebuild is caught at boot by a lock-hash mismatch and fails loudly.

---

## 11. API Surface

### 11.1 Consumed by Agora ConvoAI

**`POST /v1/chat/completions`** — the load-bearing endpoint. OpenAI-compatible, `stream=true` only.

```
Authorization: Bearer <AGORA_LLM_SHARED_SECRET>       # rejected 401 if absent — this endpoint spends money
Content-Type: application/json

{ "model": "resolvix-campus_akgec",
  "messages": [ {"role":"system","content":"..."}, {"role":"user","content":"my hostel gate is locked"} ],
  "stream": true,
  "session_id": "sess_9f2c",            # <- passthrough from llm.params
  "channel":    "call_9f2c",
  "domain":     "campus_akgec",
  "caller_id":  "+9198XXXXXXXX" }
```

Response: `text/event-stream` of `chat.completion.chunk` objects, terminated by `data: [DONE]`. Guarantees:

- **Never returns `tool_calls`.** Tools execute in-process; Agora sees only speakable text.
- **Control tokens are stripped** by `sse.py` before the first delta leaves (§6.3).
- **Unknown `session_id` self-heals** — a fresh session is created rather than 400ing, because a 400 here is dead air.
- **Client disconnect cancels the turn** within one event-loop tick (§5.4b).
- **First delta inside 600 ms or the answer path is abandoned** (§9.2 row 7).

**`GET /v1/models`** — returns `resolvix-<domain>`; ConvoAI's provisioning validation calls it.

### 11.2 Call lifecycle

| Method | Path | Contract |
|---|---|---|
| `POST` | `/calls` | `{caller_id?, domain?}` → `201 {session_id, channel, uid, token, expires_at, greeting_url}`. Returns before the agent joins (§4.6). p99 ≤ 150 ms |
| `POST` | `/rtc/token` | `{channel, uid, role}` → `{token, expires_at}`. TTL 3600 s |
| `GET` | `/calls/{session_id}` | Session snapshot, redacted; powers the live dashboard tile |
| `POST` | `/calls/{session_id}/transfer` | `{queue, reason}` → `202 {staff_token, staff_uid}`. Notifies on-shift staff over `WS /ws/agents`; on `TRANSFER_TIMEOUT_MS` expiry auto-creates a `transfer_failed` ticket |
| `POST` | `/calls/{session_id}/interrupt` | Server-initiated barge-in (§5.4c) → ConvoAI `/interrupt` |
| `POST` | `/calls/{session_id}/speak` | `{text}` — push a line through ConvoAI TTS without an LLM turn; used for handoff narration and deadline-breach lines |
| `DELETE` | `/calls/{session_id}` | ConvoAI `/leave`, finalise session, persist transcript |
| `WS` | `/ws/agents` | Staff console: presence, `transfer_request`, `ticket_created`, live urgency tiles |

### 11.3 Tickets and calibration

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/tickets?queue=&status=&priority_min=` | **Kept from v1** (`main.py:400`); `category` param accepted as a deprecated alias for `queue` for one release so `department.html` keeps working during the migration |
| `POST` | `/api/tickets` | Requires `Idempotency-Key`; returns the existing ticket on replay |
| `PATCH` | `/api/tickets/{id}/status` | **Kept from v1** (`main.py:409`) |
| `POST` | `/api/tickets/{id}/feedback` | `{verdict}` → feeds `calibration_events` (§6.5) |
| `GET` | `/api/insights` | **Kept from v1** (`main.py:374`), extended with `p50_first_audio_ms`, `p95_first_audio_ms`, `cache_hit_rate`, `transfer_rate`, `route_breakdown`, `unanswered_top_20` |
| `GET` | `/api/thresholds` · `POST /api/thresholds/recalibrate` | Inspect and re-run calibration; returns the proposed diff and the cost delta before activation |

### 11.4 PSTN (Phase 5) and ops

`POST /pstn/twilio/voice` (TwiML) · `WS /pstn/twilio/stream` (bidirectional media) · `GET /healthz` (liveness) · `GET /readyz` (index loaded, pack valid, Agora reachable) · `GET /metrics`.

**Deleted from v1:** `POST /voice`, `/menu`, `/handle-query`, `/clarify-1`, `/clarify-2`, `/collect-name`, `/collect-roll`, `/anything-else`, and `POST /api/query`.

---

## 12. Migration Plan

### 12.1 Deleted

| Path | Lines | Reason |
|---|---|---|
| `Resolvix/main.py` | 62–289 | All 8 TwiML endpoints. The DTMF menu, `Gather`/`Say` turn cycle and per-endpoint state machine are exactly what the rebuild removes |
| `Resolvix/main.py` | 27 | `from twilio.twiml.voice_response import VoiceResponse, Gather` |
| `Resolvix/main.py` | 50 | `SESSIONS: dict[str, dict]` → `core/session/store.py` |
| `Resolvix/main.py` | 52–55 | `VOICE_LANG`, `CLARIFY_Q1`, `CLARIFY_Q2` → `domain.yaml` / `prompts/clarify.md` |
| `Resolvix/main.py` | 332–358 | `POST /api/query` — a turn-based contract with an `attempt` counter; no analogue in a streaming flow |
| `Resolvix/rag.py` | 48–55 | `CATEGORY_FILES` digit map → `queue` front matter |
| `Resolvix/rag.py` | 57–64, `ticket_store.py` 28–35 | `CATEGORY_LABELS`, duplicated in two modules → `domain.yaml: queues` (single definition) |
| `Resolvix/rag.py` | 112, 126–143 | `TfidfVectorizer` + cosine search → `hybrid_index.py` |
| `Resolvix/rag.py` | 204, 212–213 | `RAG_CONFIDENCE_THRESHOLD` score floor → `answerability` (§6.3) |
| `Resolvix/ticket_store.py` | 19–26 | `TEAM_ENV_MAP` digit→env-var map → `escalation.yaml: destinations` |
| `Resolvix/ticket_store.py` | 37–47 | `URGENCY_KEYWORDS` + `detect_urgency()` — the thing §6 replaces. **Hard-deleted, and CI-guarded against return** |
| `Resolvix/campus-helpdesk-prototype.html` | 605 | A click-through mock of the deleted turn-based flow; superseded by `web/caller.html` |
| `data/markdown-csv.py`, `data/rag_cleaned_2.json`, `data/raw_data.txt`, `data/fit_data.txt` | — | Corrupt (documented in `DATA_SOURCES.md`) or superseded intermediates |

### 12.2 Refactored

| From | To | Change |
|---|---|---|
| `rag.py:75-105` `_chunk_markdown` | `core/retrieval/chunking.py` | **Ported nearly verbatim.** Comment-stripping, `## Contact` boilerplate drop and heading-only-chunk drop are all earned behaviour. Added: YAML front-matter parse, per-section `provenance` and `answer_hint` extraction |
| `rag.py:32-46` `_stem` / `_stemming_tokenizer` | `core/retrieval/hybrid_index.py` | Kept as the BM25 tokeniser. The reason v1 gives (dropped chunks, not just worse ranking) applies identically to BM25 |
| `rag.py:153-188` `_phrase_answer` | `core/graph/nodes/answer.py` | Now streaming; system prompt moves to `prompts/system.md`; the `NOT_ANSWERABLE` post-hoc check becomes the first-token `<G>`/`<NG>` control token |
| `rag.py:191-225` `answer_query` | `core/graph/nodes/retrieve.py` + `decide.py` | Split: retrieval no longer decides. It scores; `policy.py` decides |
| `ticket_store.py:50-84` `_get_conn` | `core/tickets/sqlite_store.py` | Keeps the guarded-ALTER migration pattern; adds WAL, the four new tables and the idempotency index |
| `ticket_store.py:87-108` `create_ticket` | same | Signature loses `roll_no`, gains `caller_attributes: dict`, `queue`, `idempotency_key`, `urgency_vector` |
| `ticket_store.py:111-138` `_notify_team` | `core/notify/adapters/whatsapp.py` | Behind the `Destination` protocol; targets are URIs from `escalation.yaml`, not env-var names |
| `ticket_store.py:190-224` `get_insights` | `core/telemetry/insights.py` | Adds latency percentiles, cache-hit rate, route breakdown |
| `main.py:400-414` `/api/tickets`, `PATCH .../status` | `core/api/tickets.py` | Contract preserved; `category` accepted as a deprecated alias so the existing dashboard is not broken by the same commit |
| `campus-helpdesk-department.html` | `web/department.html` | Fix `API_BASE` port mismatch (Audit item 7); add a **Join call** button (Agora Web SDK + token), a transfer-request toast over `WS /ws/agents`, and the four feedback verdict buttons that feed calibration |
| `Resolvix/docs/*.md` | `domains/campus_akgec/corpus/*.md` | Content unchanged; front matter added |
| `Resolvix/DATA_SOURCES.md` | `domains/campus_akgec/PROVENANCE.md` | Moved; per-section `provenance` markers now machine-read, not just human-audited |
| `data/Eda.ipynb`, `Upload_data.ipynb`, `web-markdown.py`, `akg_links.txt`, `akg_data.csv`, `akgec_markdown.csv` | `research/` | Out of the runtime path, retained for corpus regeneration |

### 12.3 New

`core/transport/*` · `core/openai_shim/*` · `core/graph/*` · `core/routing/*` (classifier, policy, calibration, availability) · `core/retrieval/hybrid_index.py`, `semantic_cache.py` · `core/notify/protocol.py` + adapters · `core/session/store.py` · `core/domain/{protocol,loader}.py` · `core/telemetry/spans.py` · `domains/campus_akgec/{domain,escalation,exemplars}.yaml`, `prompts/`, `tools.py` · `domains/clinic_demo/*` · `web/caller.html` · `tests/test_domain_boundary.py` · `importlinter.ini` · `Makefile` (`build-index`, `bench`, `prove-swappable`) · `.env.example` (rewritten, and **removed from `.gitignore`** — Audit item 7).

### 12.4 Sequencing

The old and new stacks coexist for two phases: v1's `/voice` webhook and the new `/v1/chat/completions` can run in the same process against the same SQLite file, because the ticket migration is additive. That means the Twilio number keeps working while the Agora path is built, and the deletion in §12.1 lands as one commit at the end of Phase 3 — not as a big-bang rewrite with no working demo in between.

---

## 13. Build Phases

Each phase ends with something callable. No phase leaves the repo undemoable.

### Phase 0 — Agora spine (2–3 days)
Token server, `POST /calls`, `web/caller.html`, ConvoAI join/leave with a **static** LLM stub that always replies "I heard you."
**Demo:** open the page, click Call, agent joins, greeting plays, interrupt it mid-sentence and it stops.
**Exit:** greeting ≤ 800 ms; barge-in verified; `AGORA_APP_CERTIFICATE` enforced (a token-less join is rejected).

### Phase 1 — OpenAI shim + Groq passthrough (2 days)
`POST /v1/chat/completions` with SSE, bearer auth, `llm.params` passthrough, per-turn cancellation, Groq `llama-3.1-8b-instant` streaming. No RAG, no tools.
**Demo:** an open-ended natural conversation with working barge-in, sub-second first audio.
**Exit:** p95 first-delta ≤ 400 ms; disconnect cancels the Groq request (assert in the log, not by inspection).

### Phase 2 — Grounded answering (3–4 days)
`chunking.py` port, `make build-index`, hybrid BM25+dense retrieval, semantic cache seeded from `answer_hint`, LangGraph with hydrate/retrieve/answer/finalize, first-token `<G>`/`<NG>` control token.
**Demo:** "When is the fee deadline?" answered from the corpus in under a second; "Can I bring my car onto campus?" produces an honest refusal rather than an invention.
**Exit:** ≥ 60 % of the 40-utterance suite answered; zero fabricated numbers on the fee/hostel set; cache hit ≤ 350 ms.

### Phase 3 — Escalation engine + tickets (3–4 days)
`classifier.py`, `policy.py`, ticket tool with idempotency, notify adapters, dashboard wiring, `escalation.yaml`. **This is the commit that deletes v1's IVR** (§12.1).
**Demo:** three consecutive calls producing answer, ticket, and transfer-attempt from utterances that share no keywords with any rule.
**Exit:** the §6.7 table reproduces on live calls; `URGENCY_KEYWORDS` is gone and CI-guarded; a cancelled ticket turn creates exactly one row.

### Phase 4 — Live transfer (2–3 days)
Human joins the same Agora channel from `department.html`; on-shift availability gating; handoff narration via `/speak`; `transfer_failed` fallback with priority bump; AI mutes and continues transcribing.
**Demo:** an urgent call, a staff toast, a human speaking to the caller inside 8 s, with the AI-written summary already on screen.
**Exit:** connect ≤ 8 s; no-answer path yields a priority ticket with the correct SLA.

### Phase 5 — PSTN ingress (2–3 days, optional)
`pstn_bridge.py`, TwiML endpoint, µ-law↔PCM resampling, greeting-before-bridge.
**Demo:** dial a real number from a real phone.
**Exit:** intelligible both directions at 8 kHz; total latency ≤ 1.9 s p95 with the +150 ms per direction accounted for; barge-in still functions on the narrower band.

### Phase 6 — Prove swappability + calibration (3 days)
`domains/clinic_demo/` (six files, no Python beyond `tools.py`), `importlinter.ini`, `test_domain_boundary.py`, feedback endpoint, `calibration.py` grid search, `/api/thresholds`.
**Demo:** `RESOLVIX_DOMAIN=clinic_demo make run`, one clinical call correctly transferring where the campus pack would have clarified, then `git diff --stat core/` printing nothing. Then 20 dashboard verdicts move `immediacy_hi` and the diff is shown.
**Exit:** `make prove-swappable` green in CI.

### Phase 7 — Latency and resilience hardening (2–3 days)
Per-stage deadlines and breach actions, `make bench` regression gate, the §8.3 degradation ladder implemented and tested by fault injection (429s, dead TTS, dead ConvoAI), `/metrics`, structured turn logs.
**Demo:** revoke `GROQ_API_KEY` mid-call; the call continues on extractive answers and the caller is never met with silence.
**Exit:** every ladder rung has a passing fault-injection test; p50/p95 within §9.2.

**Critical path to a credible demo: Phases 0–4** (~12–17 days). Phases 5–7 are hardening and the swappability proof.

---

## 14. Open Questions & Risks

| ID | Risk | Impact | Likelihood | Mitigation / trigger |
|---|---|---|---|---|
| R1 | **Agora ConvoAI Engine free allowance is a trial, not a standing free tier, and is billed separately from the 10k RTC minutes** | Blocks the mandated architecture | High | Instrument agent-minutes from Phase 0 and display remaining budget in `/api/insights`. Fallback path (§4.2) is designed and costed at +400–600 ms, not hypothetical. **Confirm exact trial terms before Phase 0.** |
| R2 | **Groq `playai-tts` is not a native ConvoAI TTS vendor**, and its free RPD is low for call volume | TTS is a hard dependency of the mandated stack | High | Two-track: attempt Groq's OpenAI-compatible `/v1/audio/speech` through ConvoAI's `openai` vendor with a base-URL override; if unsupported, Azure Speech F0 via native `vendor: microsoft` (0.5 M chars/mo ≈ 900 three-minute calls). Fixed lines pre-rendered to WAV either way. **Validate in Phase 0, not Phase 4.** |
| R3 | Groq Whisper cannot be used as ConvoAI's ASR either | The mandated STT choice only exists on the self-hosted path | High | Accepted and documented: ConvoAI's bundled ASR is primary because it is in-media-path; Groq Whisper is the fallback-path STT. Stated as A2 rather than hidden. |
| R4 | Groq free-tier 429s under demo load (classifier + answer = 2 calls/turn) | Mid-call stalls | Medium | Classifier is droppable by design (§6.6); semantic cache removes the LLM entirely for the top ~40 questions; extractive fallback exists. Consider a second Groq key on a second email — within the stated one-email-per-service constraint per account. |
| R5 | Barge-in false positives on noisy Indian phone lines | Agent constantly cut off; call unusable | Medium | `enable_bhvs` + `enable_aivad`; `interrupt_duration_ms` tuned on real recordings in Phase 5, not on a laptop mic. Instrument `interrupts_per_minute` and alert above 4. |
| R6 | 8 kHz µ-law PSTN audio degrades ASR, particularly on roll numbers and rupee amounts | Wrong ticket data, misheard identity | Medium | Read back every captured slot for confirmation; regex-validate against `identity_fields.pattern`; prefer the web caller path for the demo. |
| R7 | Classifier miscalibration causes systematic over-transfer, burning the very staff time the product saves | Product-level failure, not a bug | Medium | Asymmetric cost function with `c_false_transfer` set high for the campus pack; `transfer_rate` on the dashboard with a target band of 5–15 %; availability gating hard-caps concurrent transfers. |
| R8 | **3 of 6 campus categories are partly `SYNTHETIC`** (`DATA_SOURCES.md`) | A confidently spoken invented fee or curfew rule is the worst outcome this system can produce | Certain (already true) | `provenance: synthetic` is machine-read: mandatory verbal hedge + `synthetic_answerability_penalty: 0.25` so those chunks escalate sooner. A demo-mode banner lists which sections are synthetic. Does **not** substitute for sourcing the real documents. |
| R9 | No dashboard auth; transcripts contain caller phone numbers and roll numbers | PII exposure | Certain (carried from v1) | Phase 4 adds a shared-secret gate at minimum; `TRANSCRIPT_RETENTION_DAYS=30` purge job; `caller_id` hashed in `query_log` while kept plain in `tickets` (staff must call back). |
| R10 | Barge-in cancelling a turn mid-tool-call | Duplicate tickets, duplicate notifications | Medium | `idempotency_key` UNIQUE index (§10.2); notify adapters keyed on `ticket_id`; a dedicated test that cancels between INSERT and confirmation. |
| R11 | `ngrok` URL rotation or Render cold start invalidates the provisioned `llm.url` | Agent joins and then fails on the first turn | High in dev | `make dev` re-reads the tunnel and re-provisions; `/readyz` checks that ConvoAI can reach us before a call is accepted. |
| R12 | Sequential thinking in the agent (retrieve → then classify) creeping back in during implementation | Silently doubles per-turn latency | Medium | `make bench` gates p95 in CI; the parallel fan-out is a structural property of the graph, and a test asserts `retrieve` and `classify` have no edge between them. |

### Open questions

1. **Does ConvoAI's `openai` TTS vendor accept a base-URL override?** Determines whether Groq PlayAI is reachable at all inside the mandated architecture. Blocks R2. Answer in Phase 0.
2. **Does ConvoAI forward arbitrary `llm.params` keys verbatim into the request body?** The entire session-correlation design (§4.3) rests on it. Fallback: encode `session_id` into the `model` string (`resolvix-campus_akgec-sess_9f2c`), which is ugly but guaranteed to survive.
3. **Is the ConvoAI free allowance metered in agent-minutes or requests?** Changes whether idle agents must be aggressively reaped. Interim: `idle_timeout: 30`.
4. **Who is "a human" for the demo?** Live transfer needs a second browser with a mic on-shift. If no second operator is available, Phase 4's demo must be staged with the same operator on a second device — decide before scripting the demo.
5. **Ticket ID readability over voice.** 8 hex characters spoken digit-by-digit is ~10 syllables and contains letters that confuse over a phone line (B/D/E, and 0/O). Proposal: a 6-character Crockford base-32 ID excluding I, L, O, U. Needs a decision before Phase 3 locks the schema.
6. **Does the campus corpus need `speak_currency_as: words`?** "Rs. 1,42,156" read literally by TTS is unintelligible. Proposed as a front-matter flag with a normaliser in the answer node; confirm whether the chosen TTS voice already handles Indian digit grouping.

---

## Assumptions

Flagged because each is a place where this document commits to something not verified against a live account or a current vendor doc.

- **A1 — Free-tier numbers are indicative, not verified.** Agora's 10,000 voice minutes/month and Groq's per-model RPM/RPD figures are stated from general knowledge of these tiers and **must be re-checked** at `console.groq.com/settings/limits` and Agora's pricing page before Phase 0. Every free-tier row in §8.2 is subject to change by the vendor. The ConvoAI Engine allowance in particular is assumed to be a *trial*, not perpetual.
- **A2 — Groq Whisper is not available as an Agora ConvoAI ASR vendor.** The PRD therefore uses ConvoAI's bundled ASR on the primary path and reserves Groq `whisper-large-v3-turbo` for the self-hosted fallback and the PSTN bridge. This deviates from the brief's "assume Groq for STT" and is called out rather than quietly satisfied.
- **A3 — Groq `playai-tts` is not a first-class ConvoAI TTS vendor.** Reachability via an OpenAI-compatible base-URL override is an assumption (Open Question 1); Azure Speech F0 is the named fallback with its free limit stated.
- **A4 — Agora forwards unrecognised `llm.params` keys into the LLM request body.** Session correlation depends on it; a documented fallback exists (Open Question 2).
- **A5 — "Helpline number" is satisfied by a browser caller page for the primary demo.** Agora does not issue phone numbers; real PSTN ingress needs a carrier, and Twilio's trial is the only zero-budget option (and restricts calls to verified numbers). PSTN is scoped as optional Phase 5.
- **A6 — Single process, single instance, one active domain pack.** No horizontal scaling, and the never-busy queue is demo-grade per the brief.
- **A7 — Human agents are reachable through an Agora Web SDK console**, not a PSTN dial-out. This is what makes live transfer free; it also means staff need a browser and a headset, not a desk phone.
- **A8 — The existing `docs/*.md` corpus is the Phase 2 knowledge base as-is**, synthetic sections included, mitigated by the hedging mechanism in §10.3 rather than by re-sourcing content.
- **A9 — Latency figures in §9.2 are design targets derived from published vendor TTFT characteristics, not measurements.** `make bench` exists specifically to replace them with real numbers by end of Phase 2.
- **A10 — `llama-3.1-8b-instant` is sufficient for extractive answering and vector classification.** Assumed because answers are grounded in retrieved text rather than generated from parametric knowledge; if the classifier proves unreliable at 8B, the escalation of choice is `llama-3.3-70b-versatile` for the classifier only, at roughly +150 ms, which then competes with the §9 budget.
- **A11 — The `data/` crawl artefacts are not needed at runtime.** They move to `research/` on the strength of `DATA_SOURCES.md`'s own audit; `rag_cleaned_2.json` is deleted on the strength of that file's "corrupt" finding rather than re-verified byte by byte.
