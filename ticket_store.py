"""
SQLite ticket store + WhatsApp escalation + lightweight query analytics.

SQLite instead of Supabase on purpose: zero external setup, works offline during
the demo, no risk of a network blip killing the pitch on stage. Swap for Supabase
post-hackathon by replacing this module's functions -- the calling code in main.py
doesn't need to change.
"""

import os
import sqlite3
import uuid
from datetime import datetime

from twilio.rest import Client

DB_PATH = os.path.join(os.path.dirname(__file__), "tickets.db")

TEAM_ENV_MAP = {
    "1": "TEAM_WHATSAPP_FEES",
    "2": "TEAM_WHATSAPP_HOSTEL",
    "3": "TEAM_WHATSAPP_EXAM",
    "4": "TEAM_WHATSAPP_ADMISSIONS",
    "5": "TEAM_WHATSAPP_PLACEMENTS",
    "6": "TEAM_WHATSAPP_OTHER",
}

CATEGORY_LABELS = {
    "1": "Fees",
    "2": "Hostel",
    "3": "Exams",
    "4": "Admissions",
    "5": "Placements",
    "6": "General / Other",
}

URGENCY_KEYWORDS = [
    "urgent", "emergency", "asap", "immediately", "right now", "today",
    "can't wait", "cannot wait", "24 hour", "24-hour", "critical", "please help fast",
]


def detect_urgency(text: str) -> str:
    """Keyword-based urgency signal. Deliberately simple and explainable for a
    demo -- swap for a small classifier later if false positives show up."""
    t = (text or "").lower()
    return "high" if any(k in t for k in URGENCY_KEYWORDS) else "normal"


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id TEXT PRIMARY KEY,
            created_at TEXT,
            category TEXT,
            name TEXT,
            roll_no TEXT,
            phone TEXT,
            query TEXT,
            status TEXT,
            urgency TEXT DEFAULT 'normal'
        )
        """
    )
    # Safe migration for tickets.db files created before the urgency column existed.
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(tickets)").fetchall()}
    if "urgency" not in existing_cols:
        conn.execute("ALTER TABLE tickets ADD COLUMN urgency TEXT DEFAULT 'normal'")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS query_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            category TEXT,
            query TEXT,
            answered INTEGER,
            urgency TEXT
        )
        """
    )
    return conn


def create_ticket(category: str, name: str, roll_no: str, phone: str, query: str, urgency: str = "normal") -> str:
    ticket_id = uuid.uuid4().hex[:8].upper()
    conn = _get_conn()
    with conn:
        conn.execute(
            "INSERT INTO tickets (id, created_at, category, name, roll_no, phone, query, status, urgency) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ticket_id,
                datetime.utcnow().isoformat(),
                category,
                name,
                roll_no,
                phone,
                query,
                "open",
                urgency,
            ),
        )
    conn.close()
    _notify_team(ticket_id, category, name, roll_no, phone, query, urgency)
    return ticket_id


def _notify_team(ticket_id, category, name, roll_no, phone, query, urgency="normal"):
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_wa = os.getenv("TWILIO_WHATSAPP_NUMBER")
    to_wa = os.getenv(TEAM_ENV_MAP.get(category, "TEAM_WHATSAPP_OTHER"))

    label = CATEGORY_LABELS.get(category, "General")
    prefix = "🚨 URGENT — " if urgency == "high" else ""
    body = (
        f"{prefix}New Helpdesk Ticket #{ticket_id}\n"
        f"Category: {label}\n"
        f"Urgency: {urgency}\n"
        f"Name: {name}\n"
        f"Roll No: {roll_no}\n"
        f"Caller: {phone}\n"
        f"Query: {query}"
    )

    if not (sid and token and from_wa and to_wa):
        # Credentials not configured -- log locally instead of crashing the call flow
        print(f"[TICKET NOTIFY - no WhatsApp creds]\n{body}")
        return

    try:
        client = Client(sid, token)
        client.messages.create(from_=from_wa, to=to_wa, body=body)
    except Exception as e:
        print(f"[TICKET NOTIFY FAILED] #{ticket_id}: {e}")


def get_ticket(ticket_id: str):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    conn.close()
    return row


def list_tickets(category: str | None = None, status: str | None = None):
    conn = _get_conn()
    query = "SELECT id, created_at, category, name, roll_no, phone, query, status, urgency FROM tickets WHERE 1=1"
    params = []
    if category:
        query += " AND category = ?"
        params.append(category)
    if status:
        query += " AND status = ?"
        params.append(status)
    # Urgent-first, then newest-first within each urgency tier
    query += " ORDER BY CASE WHEN urgency = 'high' THEN 0 ELSE 1 END, created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    cols = ["id", "created_at", "category", "name", "roll_no", "phone", "query", "status", "urgency"]
    return [dict(zip(cols, row)) for row in rows]


def update_status(ticket_id: str, status: str) -> bool:
    conn = _get_conn()
    with conn:
        cur = conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
    conn.close()
    return cur.rowcount > 0


def log_query(category: str, query: str, answered: bool, urgency: str = "normal"):
    """Fire-and-forget analytics log -- every question asked, answered or not.
    This is the raw material for /api/insights; never let a logging failure
    break the actual answer/escalation flow."""
    try:
        conn = _get_conn()
        with conn:
            conn.execute(
                "INSERT INTO query_log (created_at, category, query, answered, urgency) VALUES (?, ?, ?, ?, ?)",
                (datetime.utcnow().isoformat(), category, query, int(answered), urgency),
            )
        conn.close()
    except Exception as e:
        print(f"[QUERY LOG FAILED]: {e}")


def get_insights():
    conn = _get_conn()

    total = conn.execute("SELECT COUNT(*) FROM query_log").fetchone()[0]
    answered = conn.execute("SELECT COUNT(*) FROM query_log WHERE answered = 1").fetchone()[0]
    escalated = total - answered

    by_category = conn.execute(
        "SELECT category, COUNT(*) FROM query_log GROUP BY category"
    ).fetchall()
    category_breakdown = {
        CATEGORY_LABELS.get(cat, cat): count for cat, count in by_category
    }

    urgent_open = conn.execute(
        "SELECT COUNT(*) FROM tickets WHERE urgency = 'high' AND status = 'open'"
    ).fetchone()[0]

    open_tickets = conn.execute("SELECT COUNT(*) FROM tickets WHERE status = 'open'").fetchone()[0]
    resolved_tickets = conn.execute("SELECT COUNT(*) FROM tickets WHERE status = 'resolved'").fetchone()[0]

    conn.close()

    escalation_rate = round((escalated / total) * 100, 1) if total else 0.0

    return {
        "total_queries": total,
        "answered_directly": answered,
        "escalated": escalated,
        "escalation_rate_pct": escalation_rate,
        "category_breakdown": category_breakdown,
        "urgent_open_tickets": urgent_open,
        "open_tickets": open_tickets,
        "resolved_tickets": resolved_tickets,
    }
