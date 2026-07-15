"""
Campus Helpdesk Triage Agent
=============================
Voice-first IVR helpdesk, built on the same Twilio call pattern as Saathi.

Call flow:
  /voice        -> greeting + menu (press 1 fees / 2 hostel / 3 exams / 4 other)
  /menu         -> stores category, asks the student to speak their question
  /handle-query -> runs RAG; if confident, speaks the answer and offers "anything else";
                   if not confident, starts the ticket-collection flow
  /collect-name -> captures name
  /collect-roll -> captures roll number, creates ticket, notifies the right team
  /anything-else-> loops back to /voice or ends the call

State is kept in-memory keyed by CallSid. Fine for a hackathon demo (single
process, single instance). For production, swap SESSIONS for Redis.
"""

import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from twilio.twiml.voice_response import VoiceResponse, Gather

from rag import answer_query, CATEGORY_LABELS
from ticket_store import create_ticket, list_tickets, update_status, log_query, get_insights, detect_urgency

app = FastAPI(title="Campus Helpdesk Triage Agent")

# Demo-only: wide open so the browser prototype (any origin, including a local
# file:// or a different dev port) can call this API directly. Lock this down
# to your actual frontend's origin before this goes anywhere near production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# call_sid -> { category, query, name, roll_no, phone }
SESSIONS: dict[str, dict] = {}

VOICE_LANG = "en-IN"  # switch to "hi-IN" for Hindi prompts

CLARIFY_Q1 = "Could you tell me a bit more detail about your question?"
CLARIFY_Q2 = "Is this urgent -- do you need it resolved within 24 hours, or can it wait a few days?"


def twiml(resp: VoiceResponse) -> Response:
    return Response(content=str(resp), media_type="application/xml")


@app.post("/voice")
async def voice(request: Request, CallSid: str = Form(...), From: str = Form(None)):
    SESSIONS[CallSid] = {"phone": From}

    resp = VoiceResponse()
    gather = Gather(
        num_digits=1,
        action="/menu",
        method="POST",
        timeout=6,
    )
    gather.say(
        "Welcome to the Campus Helpdesk. "
        "For fee related questions, press 1. "
        "For hostel related questions, press 2. "
        "For exam related questions, press 3. "
        "For admissions, press 4. "
        "For placements, press 5. "
        "For anything else, press 6.",
        voice="Polly.Aditi",
        language=VOICE_LANG,
    )
    resp.append(gather)
    resp.say("We did not receive any input. Goodbye.", voice="Polly.Aditi", language=VOICE_LANG)
    return twiml(resp)


@app.post("/menu")
async def menu(request: Request, CallSid: str = Form(...), Digits: str = Form(None)):
    session = SESSIONS.setdefault(CallSid, {})

    if Digits not in CATEGORY_LABELS:
        resp = VoiceResponse()
        resp.say("Sorry, that's not a valid option.", voice="Polly.Aditi", language=VOICE_LANG)
        resp.redirect("/voice", method="POST")
        return twiml(resp)

    session["category"] = Digits

    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/handle-query",
        method="POST",
        speech_timeout="auto",
        language=VOICE_LANG,
    )
    gather.say(
        f"You selected {CATEGORY_LABELS[Digits]}. "
        "Please speak your question after the beep.",
        voice="Polly.Aditi",
        language=VOICE_LANG,
    )
    resp.append(gather)
    resp.say("We did not catch that. Goodbye.", voice="Polly.Aditi", language=VOICE_LANG)
    return twiml(resp)


@app.post("/handle-query")
async def handle_query(
    request: Request, CallSid: str = Form(...), SpeechResult: str = Form(None)
):
    session = SESSIONS.setdefault(CallSid, {})
    category = session.get("category", "4")
    query_text = SpeechResult or ""
    session["query"] = query_text
    session["clarify_context"] = []

    resp = VoiceResponse()

    if not query_text.strip():
        resp.say("Sorry, I didn't catch that.", voice="Polly.Aditi", language=VOICE_LANG)
        resp.redirect("/menu", method="POST")
        return twiml(resp)

    result = answer_query(query_text, category=category)

    if result.answer:
        log_query(category, query_text, answered=True)
        resp.say(result.answer, voice="Polly.Aditi", language=VOICE_LANG)
        gather = Gather(
            num_digits=1, action="/anything-else", method="POST", timeout=5
        )
        gather.say(
            "Press 1 if you have another question, or press 2 to end the call.",
            voice="Polly.Aditi",
            language=VOICE_LANG,
        )
        resp.append(gather)
        resp.say("Thank you for calling. Goodbye.", voice="Polly.Aditi", language=VOICE_LANG)
    else:
        # Not confident yet -- ask a targeted follow-up before jumping to a ticket.
        resp.say(CLARIFY_Q1, voice="Polly.Aditi", language=VOICE_LANG)
        gather = Gather(
            input="speech", action="/clarify-1", method="POST",
            speech_timeout="auto", language=VOICE_LANG,
        )
        resp.append(gather)

    return twiml(resp)


@app.post("/clarify-1")
async def clarify_1(
    request: Request, CallSid: str = Form(...), SpeechResult: str = Form(None)
):
    session = SESSIONS.setdefault(CallSid, {})
    detail = SpeechResult or ""
    session["clarify_context"] = [detail]

    combined = f"{session.get('query', '')} {detail}"
    result = answer_query(combined, category=session.get("category", "4"))

    resp = VoiceResponse()
    if result.answer:
        log_query(session.get("category", "4"), session.get("query", ""), answered=True)
        resp.say(result.answer, voice="Polly.Aditi", language=VOICE_LANG)
        gather = Gather(num_digits=1, action="/anything-else", method="POST", timeout=5)
        gather.say(
            "Press 1 if you have another question, or press 2 to end the call.",
            voice="Polly.Aditi", language=VOICE_LANG,
        )
        resp.append(gather)
        resp.say("Thank you for calling. Goodbye.", voice="Polly.Aditi", language=VOICE_LANG)
    else:
        resp.say(CLARIFY_Q2, voice="Polly.Aditi", language=VOICE_LANG)
        gather = Gather(
            input="speech", action="/clarify-2", method="POST",
            speech_timeout="auto", language=VOICE_LANG,
        )
        resp.append(gather)

    return twiml(resp)


@app.post("/clarify-2")
async def clarify_2(
    request: Request, CallSid: str = Form(...), SpeechResult: str = Form(None)
):
    session = SESSIONS.setdefault(CallSid, {})
    urgency_answer = SpeechResult or ""
    session["clarify_context"] = session.get("clarify_context", []) + [urgency_answer]

    combined = f"{session.get('query', '')} " + " ".join(session["clarify_context"])
    urgency = detect_urgency(combined)
    session["urgency"] = urgency
    session["query"] = combined  # enrich the ticket with everything gathered so far
    log_query(session.get("category", "4"), session.get("query", ""), answered=False, urgency=urgency)

    resp = VoiceResponse()
    resp.say(
        "I'm not confident I can answer that correctly, so I'll create a ticket "
        "for our team to follow up. Please tell me your full name after the beep.",
        voice="Polly.Aditi",
        language=VOICE_LANG,
    )
    gather = Gather(
        input="speech", action="/collect-name", method="POST",
        speech_timeout="auto", language=VOICE_LANG,
    )
    resp.append(gather)
    return twiml(resp)


@app.post("/collect-name")
async def collect_name(
    request: Request, CallSid: str = Form(...), SpeechResult: str = Form(None)
):
    session = SESSIONS.setdefault(CallSid, {})
    session["name"] = SpeechResult or "Unknown"

    resp = VoiceResponse()
    gather = Gather(
        num_digits=10,
        action="/collect-roll",
        method="POST",
        timeout=8,
        finish_on_key="#",
    )
    gather.say(
        "Thank you. Please enter your roll number using the keypad, then press hash.",
        voice="Polly.Aditi",
        language=VOICE_LANG,
    )
    resp.append(gather)
    return twiml(resp)


@app.post("/collect-roll")
async def collect_roll(
    request: Request, CallSid: str = Form(...), Digits: str = Form(None)
):
    session = SESSIONS.setdefault(CallSid, {})
    session["roll_no"] = Digits or "Unknown"

    ticket_id = create_ticket(
        category=session.get("category", "4"),
        name=session.get("name", "Unknown"),
        roll_no=session.get("roll_no", "Unknown"),
        phone=session.get("phone", "Unknown"),
        query=session.get("query", ""),
        urgency=session.get("urgency", "normal"),
    )

    resp = VoiceResponse()
    resp.say(
        f"Your ticket number is {' '.join(ticket_id)}. "
        "Our team will follow up with you shortly. Thank you for calling. Goodbye.",
        voice="Polly.Aditi",
        language=VOICE_LANG,
    )
    return twiml(resp)


@app.post("/anything-else")
async def anything_else(
    request: Request, CallSid: str = Form(...), Digits: str = Form(None)
):
    resp = VoiceResponse()
    if Digits == "1":
        resp.redirect("/voice", method="POST")
    else:
        resp.say("Thank you for calling the Campus Helpdesk. Goodbye.", voice="Polly.Aditi", language=VOICE_LANG)
    return twiml(resp)


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# JSON API for the browser prototype (campus-helpdesk-prototype.html).
# Separate from the Twilio Form-encoded webhooks above -- same underlying
# rag.py / ticket_store.py logic, just a plain JSON in/out shape for fetch().
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    category: str          # "1" fees, "2" hostel, "3" exams, "4" other
    query: str
    attempt: int = 0       # 0 = first try, 1 = after clarify Q1, 2 = after clarify Q2
    context: list[str] = []  # student's answers to prior clarifying questions, in order


class QueryResponse(BaseModel):
    action: str             # "answered" | "clarify" | "escalate"
    answer: str | None = None
    clarify_question: str | None = None
    urgency: str | None = None
    confidence: float = 0.0


class TicketRequest(BaseModel):
    category: str
    name: str
    roll_no: str
    query: str
    phone: str = "web-prototype"
    urgency: str = "normal"


class TicketResponse(BaseModel):
    ticket_id: str
    team: str


@app.post("/api/query", response_model=QueryResponse)
async def api_query(payload: QueryRequest):
    # Only the first clarifying answer (topic detail) feeds back into retrieval.
    # The second clarifying answer is an urgency check, not topical content --
    # mixing it into the retrieval query risks false-matching on words like
    # "urgent" appearing in unrelated doc text, so it's deliberately excluded here.
    detail_context = payload.context[:1]
    combined = " ".join([payload.query] + detail_context) if detail_context else payload.query

    if payload.attempt >= 2:
        # Already tried twice (raw query, then query+detail). This third turn's
        # job is purely to capture urgency and escalate -- no more retrieval.
        urgency = detect_urgency(" ".join(payload.context))
        log_query(payload.category, payload.query, answered=False, urgency=urgency)
        return QueryResponse(action="escalate", urgency=urgency, confidence=0.0)

    result = answer_query(combined, category=payload.category)

    if result.answer:
        log_query(payload.category, payload.query, answered=True)
        return QueryResponse(action="answered", answer=result.answer, confidence=result.confidence)

    # Not confident yet -- ask a targeted follow-up instead of escalating immediately.
    if payload.attempt == 0:
        return QueryResponse(action="clarify", clarify_question=CLARIFY_Q1, confidence=result.confidence)
    else:
        return QueryResponse(action="clarify", clarify_question=CLARIFY_Q2, confidence=result.confidence)


@app.post("/api/ticket", response_model=TicketResponse)
async def api_ticket(payload: TicketRequest):
    ticket_id = create_ticket(
        category=payload.category,
        name=payload.name,
        roll_no=payload.roll_no,
        phone=payload.phone,
        query=payload.query,
        urgency=payload.urgency,
    )
    return TicketResponse(ticket_id=ticket_id, team=CATEGORY_LABELS.get(payload.category, "General"))


@app.get("/api/insights")
async def api_insights():
    return get_insights()


# ---------------------------------------------------------------------------
# Department-side API -- powers the staff dashboard (campus-helpdesk-department.html).
# ---------------------------------------------------------------------------

class TicketOut(BaseModel):
    id: str
    created_at: str
    category: str
    category_label: str
    name: str
    roll_no: str
    phone: str
    query: str
    status: str
    urgency: str


class StatusUpdateRequest(BaseModel):
    status: str  # "open" | "resolved"


@app.get("/api/tickets", response_model=list[TicketOut])
async def api_list_tickets(category: str | None = None, status: str | None = None):
    rows = list_tickets(category=category, status=status)
    return [
        TicketOut(**row, category_label=CATEGORY_LABELS.get(row["category"], "General"))
        for row in rows
    ]


@app.patch("/api/tickets/{ticket_id}/status")
async def api_update_ticket_status(ticket_id: str, payload: StatusUpdateRequest):
    ok = update_status(ticket_id, payload.status)
    if not ok:
        return Response(status_code=404)
    return {"id": ticket_id, "status": payload.status}
