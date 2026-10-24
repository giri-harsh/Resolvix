"""Server-Sent Events (SSE) hub for real-time dashboard updates."""
import asyncio
import json
from datetime import datetime, timezone
from typing import Any


class SSEHub:
    """In-process pub/sub hub for SSE events.
    
    Event names: call.started, call.turn, call.ended, ticket.created, ticket.updated, alert.p1, gap.created
    """
    
    def __init__(self):
        self._subscribers: dict[int, asyncio.Queue] = {}
        self._next_subscriber_id = 0
        self._loop: asyncio.AbstractEventLoop | None = None
    
    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """Capture the event loop at startup (called from lifespan)."""
        self._loop = loop
    
    def subscribe(self) -> tuple[int, asyncio.Queue]:
        """Subscribe to events.
        
        Returns:
            (subscriber_id, queue): Queue will receive (event_name, data_dict) tuples
        """
        subscriber_id = self._next_subscriber_id
        self._next_subscriber_id += 1
        
        # Bounded queue: maxsize 100, when full drop oldest
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers[subscriber_id] = queue
        
        return subscriber_id, queue
    
    def unsubscribe(self, subscriber_id: int):
        """Unsubscribe from events."""
        self._subscribers.pop(subscriber_id, None)
    
    def publish(self, event_name: str, data: dict[str, Any]):
        """Publish an event to all subscribers.
        
        Can be called safely from sync endpoints running in the threadpool.
        Always includes 'ts' (UTC ISO with Z).
        
        Args:
            event_name: Event name (e.g., "call.started")
            data: Event data (JSON-serializable dict)
        """
        if self._loop is None:
            # Not yet initialized (shouldn't happen in normal flow)
            return
        
        # Add timestamp if not present
        if "ts" not in data:
            data["ts"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        # Publish to all subscribers (thread-safe)
        self._loop.call_soon_threadsafe(self._publish_sync, event_name, data)
    
    def _publish_sync(self, event_name: str, data: dict[str, Any]):
        """Internal: publish to all subscribers (runs in event loop thread)."""
        for subscriber_id, queue in list(self._subscribers.items()):
            try:
                if queue.full():
                    # Drop oldest message
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                
                # Add new message
                queue.put_nowait((event_name, data))
            except Exception as e:
                # Log and continue
                print(f"Error publishing to subscriber {subscriber_id}: {e}")
    
    def subscriber_count(self) -> int:
        """Get current subscriber count (for testing)."""
        return len(self._subscribers)


# Global hub instance
hub = SSEHub()
