"""Per-turn asyncio Task registry (§5.4b).

Two cancellation triggers, not one: client disconnect (the PRD's original design)
AND a new turn arriving for the same session while an old one is still running.
The second one is load-bearing — live-tested barge-in froze the call ("agent audio
stops, but no new turn ever starts, call goes dead"). request.is_disconnected()
depends on ConvoAI actually closing the HTTP connection promptly, and through a
tunnel (ngrok in testing; a real deploy may differ) that signal is not guaranteed
to arrive in time, or at all, before ConvoAI's own retry/next-turn logic gives up.
Rather than trust that signal, a same-session turn arrival cancels the previous
turn itself — the new request's existence is proof the old one should die, no
disconnect detection required.
"""
import asyncio
import logging

logger = logging.getLogger("resolvix.shim.cancel")

_ACTIVE_TASKS: dict[str, asyncio.Task] = {}          # turn_id -> Task
_SESSION_CURRENT_TURN: dict[str, str] = {}            # session_id -> turn_id


def register(turn_id: str, task: asyncio.Task, session_id: str) -> None:
    _ACTIVE_TASKS[turn_id] = task

    prior_turn_id = _SESSION_CURRENT_TURN.get(session_id)
    if prior_turn_id and prior_turn_id != turn_id:
        prior_task = _ACTIVE_TASKS.get(prior_turn_id)
        if prior_task and not prior_task.done():
            logger.info(
                "new turn_id=%s for session=%s arrived while turn_id=%s still running — cancelling it",
                turn_id, session_id, prior_turn_id,
            )
            prior_task.cancel()
    _SESSION_CURRENT_TURN[session_id] = turn_id


def unregister(turn_id: str, session_id: str) -> None:
    _ACTIVE_TASKS.pop(turn_id, None)
    if _SESSION_CURRENT_TURN.get(session_id) == turn_id:
        _SESSION_CURRENT_TURN.pop(session_id, None)


async def watch_disconnect(request, turn_id: str) -> None:
    """Sibling task: poll for client disconnect, cancel the turn's task on detection.
    Kept as a second, independent trigger — cheap, and catches the case where the
    client vanishes without ever sending a follow-up turn at all."""
    while turn_id in _ACTIVE_TASKS:
        if await request.is_disconnected():
            task = _ACTIVE_TASKS.get(turn_id)
            if task and not task.done():
                logger.info("client disconnected mid-turn, cancelling turn_id=%s", turn_id)
                task.cancel()
            return
        await asyncio.sleep(0.1)
