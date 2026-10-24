"""SQLite ticket store — schema per PRD §10.2, WAL mode, guarded-ALTER migration
pattern for future schema changes.

Ticket ID: PRD Open Question 5 leaves 8-hex-digit-by-digit vs. a shorter scheme as an
open decision. Picked here: 6-character Crockford base32 excluding I/L/O/U (the PRD's
own proposal) — fewer syllables over a bad phone line, no letters that get confused
with digits.
"""
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # excludes I, L, O, U

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "resolvix.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
  id                TEXT PRIMARY KEY,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL,
  domain            TEXT NOT NULL,
  queue             TEXT NOT NULL,
  session_id        TEXT NOT NULL,
  channel           TEXT,
  caller_id         TEXT,
  caller_attributes TEXT NOT NULL DEFAULT '{}',
  summary           TEXT NOT NULL,
  transcript        TEXT NOT NULL,
  intent            TEXT,
  urgency_vector    TEXT NOT NULL,
  immediacy         REAL NOT NULL,
  priority          INTEGER NOT NULL,
  route             TEXT NOT NULL,
  status            TEXT NOT NULL DEFAULT 'open',
  sla_due_at        TEXT,
  assigned_to       TEXT,
  resolution        TEXT,
  idempotency_key   TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_tickets_idem ON tickets(idempotency_key);
CREATE INDEX IF NOT EXISTS ix_tickets_queue_status ON tickets(queue, status, priority DESC, created_at DESC);

CREATE TABLE IF NOT EXISTS calibration_events (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at     TEXT NOT NULL,
  domain         TEXT NOT NULL,
  ticket_id      TEXT,
  session_id     TEXT NOT NULL,
  vector         TEXT NOT NULL,
  actual_route   TEXT NOT NULL,
  verdict        TEXT NOT NULL,
  labelled_by    TEXT
);

CREATE TABLE IF NOT EXISTS thresholds (
  version     TEXT PRIMARY KEY,
  domain      TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  values_json TEXT NOT NULL,
  n_labels    INTEGER NOT NULL,
  cost        REAL NOT NULL,
  active      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS query_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL, domain TEXT, queue TEXT, query TEXT,
  answered   INTEGER, route TEXT, answerability REAL, immediacy REAL,
  cache_hit  INTEGER, first_audio_ms INTEGER
);
"""


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(SCHEMA)


def _new_ticket_id() -> str:
    return "".join(secrets.choice(CROCKFORD_ALPHABET) for _ in range(6))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteTicketStore:
    def __init__(self):
        init_db()

    def create_ticket(
        self,
        *,
        domain: str,
        queue: str,
        session_id: str,
        channel: str | None,
        caller_id: str | None,
        caller_attributes: dict,
        summary: str,
        transcript: list,
        intent: str | None,
        urgency_vector: dict,
        immediacy: float,
        priority: int,
        route: str,
        sla_due_at: str | None,
        idempotency_key: str,
    ) -> dict:
        with _conn() as conn:
            existing = conn.execute(
                "SELECT * FROM tickets WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing:
                return dict(existing)

            ticket_id = _new_ticket_id()
            now = _now()
            conn.execute(
                """INSERT INTO tickets (id, created_at, updated_at, domain, queue, session_id,
                   channel, caller_id, caller_attributes, summary, transcript, intent,
                   urgency_vector, immediacy, priority, route, status, sla_due_at,
                   idempotency_key)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ticket_id, now, now, domain, queue, session_id, channel, caller_id,
                    json.dumps(caller_attributes), summary, json.dumps(transcript), intent,
                    json.dumps(urgency_vector), immediacy, priority, route, "open",
                    sla_due_at, idempotency_key,
                ),
            )
            row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            return dict(row)

    def get_ticket(self, ticket_id: str) -> dict | None:
        with _conn() as conn:
            row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            return dict(row) if row else None

    def list_tickets(self, queue: str | None = None, status: str | None = None, priority_min: int | None = None, session_id: str | None = None) -> list[dict]:
        query = "SELECT * FROM tickets WHERE 1=1"
        params: list = []
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        if queue:
            query += " AND queue = ?"
            params.append(queue)
        if status:
            query += " AND status = ?"
            params.append(status)
        if priority_min is not None:
            query += " AND priority >= ?"
            params.append(priority_min)
        query += " ORDER BY priority DESC, created_at DESC"
        with _conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def update_status(self, ticket_id: str, status: str, resolution: str | None = None) -> dict | None:
        with _conn() as conn:
            conn.execute(
                "UPDATE tickets SET status = ?, resolution = COALESCE(?, resolution), updated_at = ? WHERE id = ?",
                (status, resolution, _now(), ticket_id),
            )
            row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            return dict(row) if row else None

    def record_feedback(self, ticket_id: str, verdict: str, labelled_by: str | None = None) -> None:
        with _conn() as conn:
            ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            if not ticket:
                return
            conn.execute(
                """INSERT INTO calibration_events (created_at, domain, ticket_id, session_id,
                   vector, actual_route, verdict, labelled_by) VALUES (?,?,?,?,?,?,?,?)""",
                (_now(), ticket["domain"], ticket_id, ticket["session_id"], ticket["urgency_vector"],
                 ticket["route"], verdict, labelled_by),
            )

    def get_calibration_events(self, domain: str) -> list[dict]:
        with _conn() as conn:
            rows = conn.execute(
                "SELECT * FROM calibration_events WHERE domain = ?", (domain,)
            ).fetchall()
            return [dict(r) for r in rows]

    def save_thresholds(self, version: str, domain: str, values: dict, n_labels: int, cost: float, active: bool) -> None:
        with _conn() as conn:
            if active:
                conn.execute("UPDATE thresholds SET active = 0 WHERE domain = ?", (domain,))
            conn.execute(
                "INSERT OR REPLACE INTO thresholds (version, domain, created_at, values_json, n_labels, cost, active) VALUES (?,?,?,?,?,?,?)",
                (version, domain, _now(), json.dumps(values), n_labels, cost, int(active)),
            )

    def get_active_thresholds(self, domain: str) -> dict | None:
        with _conn() as conn:
            row = conn.execute(
                "SELECT * FROM thresholds WHERE domain = ? AND active = 1 ORDER BY created_at DESC LIMIT 1", (domain,)
            ).fetchone()
            return dict(row) if row else None

    def log_query(self, **kwargs) -> None:
        with _conn() as conn:
            conn.execute(
                """INSERT INTO query_log (created_at, domain, queue, query, answered, route,
                   answerability, immediacy, cache_hit, first_audio_ms) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    _now(), kwargs.get("domain"), kwargs.get("queue"), kwargs.get("query"),
                    int(kwargs.get("answered", False)), kwargs.get("route"),
                    kwargs.get("answerability"), kwargs.get("immediacy"),
                    int(kwargs.get("cache_hit", False)), kwargs.get("first_audio_ms"),
                ),
            )

    def get_insights(self) -> dict:
        with _conn() as conn:
            total = conn.execute("SELECT COUNT(*) c FROM query_log").fetchone()["c"]
            answered = conn.execute("SELECT COUNT(*) c FROM query_log WHERE answered = 1").fetchone()["c"]
            cache_hits = conn.execute("SELECT COUNT(*) c FROM query_log WHERE cache_hit = 1").fetchone()["c"]
            routes = conn.execute("SELECT route, COUNT(*) c FROM query_log GROUP BY route").fetchall()
            unanswered = conn.execute(
                "SELECT query, COUNT(*) c FROM query_log WHERE answered = 0 GROUP BY query ORDER BY c DESC LIMIT 20"
            ).fetchall()
            latencies = sorted(
                r["first_audio_ms"] for r in conn.execute(
                    "SELECT first_audio_ms FROM query_log WHERE first_audio_ms IS NOT NULL"
                ).fetchall()
            )

            def _pct(p: float) -> float | None:
                if not latencies:
                    return None
                idx = min(len(latencies) - 1, int(len(latencies) * p))
                return latencies[idx]

            return {
                "total_queries": total,
                "answered_rate": (answered / total) if total else 0.0,
                "cache_hit_rate": (cache_hits / total) if total else 0.0,
                "route_breakdown": {r["route"]: r["c"] for r in routes},
                "transfer_rate": next((r["c"] / total for r in routes if r["route"] == "transfer"), 0.0) if total else 0.0,
                "unanswered_top_20": [dict(r) for r in unanswered],
                "p50_first_audio_ms": _pct(0.50),
                "p95_first_audio_ms": _pct(0.95),
            }
