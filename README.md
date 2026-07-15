# Campus Helpdesk Triage Agent

Voice-first IVR helpdesk for routine campus queries (fees, hostel, exams, general).
Built on the same call/IVR pattern as our Saathi project (missed-call access, Twilio
IVR, WhatsApp escalation) — reused deliberately so the plumbing that already works
doesn't have to be re-proven.

## How it works

```
Student calls in
  -> IVR menu: 1 Fees / 2 Hostel / 3 Exams / 4 Admissions / 5 Placements / 6 Other
  -> Speaks question
  -> RAG retrieval over trusted docs (docs/*.md) for that category
  -> Confident?  -> answer read aloud, then "anything else?"
  -> Not confident? -> collect name + roll number -> create ticket
                        -> WhatsApp ping to the right team
```

- Retrieval: TF-IDF (scikit-learn) over markdown docs, chunked by `##` heading.
  Chosen over an embedding model to avoid any model download at runtime — fully
  offline, sub-second, reliable on stage.
- Generation: Groq (`llama-3.1-8b-instant` by default) phrases the final spoken
  answer strictly from the retrieved chunks, and is explicitly instructed to
  reply `NOT_ANSWERABLE` if the chunks don't actually answer the question. This
  is the real "safe refusal" check — see limitation below.
- Tickets: SQLite (`tickets.db`, auto-created) — zero setup, no external
  dependency to fail during a live demo. Swap for Supabase later by editing
  only `ticket_store.py`.
- Escalation: Twilio WhatsApp message to a per-category team number.

## ⚠️ Known limitation — set GROQ_API_KEY before demoing

Retrieval score (TF-IDF) is keyword overlap, not true relevance. A query like
*"can I keep a pet dog in my hostel room"* can score **higher** against the
"Room Allotment" chunk (shared word: "room") than a genuinely relevant query
scores against its correct chunk. No retrieval-score threshold can fix this —
the irrelevant case can outrank the relevant one.

The actual safety net is Groq's `NOT_ANSWERABLE` check, which reads the
question and the chunk together and can tell they don't match. **Without a
Groq key, the app falls back to trusting the top-scored chunk directly** —
it will still work for the demo but the "safe refusal on uncertainty" claim
in the problem statement is not fully backed without Groq configured. It
prints a warning to the console in that mode. Test your actual demo queries
against the deployed instance beforehand.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in TWILIO_*, GROQ_API_KEY, TEAM_WHATSAPP_* in .env
```

Run locally:
```bash
uvicorn main:app --reload --port 8000
```

Expose it (for Twilio to reach it) with ngrok:
```bash
ngrok http 8000
```

In the Twilio Console, set your phone number's "A call comes in" webhook to:
```
https://<your-ngrok-or-render-url>/voice     (HTTP POST)
```

For the WhatsApp escalation, use the Twilio WhatsApp Sandbox (or a registered
WhatsApp sender) and set `TWILIO_WHATSAPP_NUMBER` / `TEAM_WHATSAPP_*` accordingly.

## Customizing the knowledge base

Drop more `.md` files into `docs/`, structured with `##` headings — each heading
becomes one retrievable chunk. Map new categories in `rag.py`
(`CATEGORY_FILES`, `CATEGORY_LABELS`) and `ticket_store.py` (`TEAM_ENV_MAP`,
`CATEGORY_LABELS`) together — both must stay in sync.

## Demo script (for judges)

1. Call the Twilio number live on stage.
2. Press **1** (Fees) → ask *"when is the fee payment deadline"* → agent
   answers instantly from the fee circular, no human involved.
3. Hang up, call again, press **2** (Hostel) → ask something genuinely
   out-of-scope, e.g. *"can I bring my car onto campus"* → agent doesn't
   guess, collects name + roll number, creates a ticket, and a WhatsApp
   message lands on the (visible, projected) team phone in real time.
4. Talking point: this is the same call infrastructure as Saathi (proven at
   [previous hackathon]) — the new part here is the retrieval + confidence
   branching + ticket routing, which is what actually solves *this*
   problem statement (staff time spent on repeat questions).

## File overview

```
main.py                          FastAPI app, Twilio IVR call flow + JSON API
rag.py                           TF-IDF retrieval + Groq-phrased, grounded answers
ticket_store.py                  SQLite tickets, urgency tagging, analytics, WhatsApp escalation
docs/                            Trusted source documents (edit these for your real campus data)
.env.example                     All required environment variables
campus-helpdesk-prototype.html   Student-side click-through demo (open directly in a browser)
campus-helpdesk-department.html  Department-side ticket dashboard (open directly in a browser)
```

Both HTML files talk to `http://localhost:8001` by default (see the `API_BASE` constant near
the top of each file's `<script>` section) -- change that if you run the backend on a
different port or deploy it somewhere else.
