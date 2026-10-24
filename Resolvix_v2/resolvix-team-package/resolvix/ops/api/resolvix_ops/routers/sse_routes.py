"""Server-Sent Events (SSE) routes."""
import asyncio
import json

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from ..deps import get_principal
from ..sse import hub as sse_hub

router = APIRouter(prefix="/v1", tags=["sse"])


@router.get("/stream")
async def stream_events(principal: dict = Depends(get_principal)):
    """Server-Sent Events for the dashboard.
    
    Event names: call.started, call.turn, call.ended, ticket.created, ticket.updated, alert.p1, gap.created
    """
    async def event_generator():
        # Subscribe to SSE hub
        subscriber_id, queue = sse_hub.subscribe()
        
        try:
            while True:
                try:
                    # Wait for event with timeout (for heartbeat)
                    event_name, data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    
                    # Yield SSE event
                    yield {
                        "event": event_name,
                        "data": json.dumps(data)
                    }
                except asyncio.TimeoutError:
                    # Send heartbeat comment
                    yield {"comment": "heartbeat"}
        
        finally:
            # Unsubscribe on disconnect
            sse_hub.unsubscribe(subscriber_id)
    
    return EventSourceResponse(event_generator())
