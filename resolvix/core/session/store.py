"""In-process SessionStore, spilled to SQLite on every route decision and at
finalisation (§10.1) — a crash loses in-flight audio but never a ticket. LangGraph
checkpointing is deliberately not used; a turn is short enough that its write cost
is pure latency.
"""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from resolvix.core.graph.state import SessionState

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "resolvix.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  domain     TEXT NOT NULL,
  channel    TEXT,
  state_json TEXT NOT NULL,
  updated_at REAL NOT NULL
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


class SessionStore:
    def __init__(self):
        init_db()
        self._live: dict[str, SessionState] = {}

    def get(self, session_id: str) -> SessionState | None:
        if session_id in self._live:
            return self._live[session_id]
        with _conn() as conn:
            row = conn.execute("SELECT state_json FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
            if row:
                state = json.loads(row["state_json"])
                self._live[session_id] = state
                return state
        return None

    def put(self, state: SessionState) -> None:
        self._live[state["session_id"]] = state

    def spill(self, state: SessionState) -> None:
        import time

        with _conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (session_id, domain, channel, state_json, updated_at) VALUES (?,?,?,?,?)",
                (state["session_id"], state["domain"], state["channel"], json.dumps(state), time.time()),
            )

    def finalize(self, session_id: str) -> None:
        state = self._live.pop(session_id, None)
        if state:
            self.spill(state)


_store: SessionStore | None = None


def get_store() -> SessionStore:
    global _store
    if _store is None:
        _store = SessionStore()
    return _store
