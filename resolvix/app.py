"""Composition root: reads RESOLVIX_DOMAIN, builds everything (§7.2).
No domain vocabulary here or under core/ — everything that gives meaning to a queue,
slot, or prompt lives in domains/<pack>/.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from resolvix import settings
from resolvix.core.domain.loader import get_pack
from resolvix.core.telemetry.logging_config import configure_logging

configure_logging()
from resolvix.core.openai_shim import routes as openai_shim_routes
from resolvix.core.tickets import routes as tickets_routes
from resolvix.core.transport import admission, pstn_bridge, token_server, transfer_ws

logger = logging.getLogger("resolvix.app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Eager warmup: building the hybrid index (embedding every corpus chunk) is a
    # blocking call. Discovered the hard way — done lazily on the first live request
    # it stalls the whole event loop for the length of that request's SSE response.
    # Boot-time is the only place this cost is allowed to land (§9's "no embedding
    # work inside a call", even though we build in-memory rather than from a
    # persisted artefact — see hybrid_index.py's module docstring).
    await asyncio.to_thread(lambda: get_pack(settings.DEFAULT_DOMAIN).retriever())
    logger.info("domain pack '%s' warmed up (corpus indexed)", settings.DEFAULT_DOMAIN)
    yield


app = FastAPI(title="Resolvix", lifespan=lifespan)

app.include_router(token_server.router)
app.include_router(admission.router)
app.include_router(openai_shim_routes.router)
app.include_router(tickets_routes.router)
app.include_router(transfer_ws.router)
app.include_router(pstn_bridge.router)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
def caller_page():
    return FileResponse(WEB_DIR / "caller.html")


@app.get("/department")
def department_page():
    return FileResponse(WEB_DIR / "department.html")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    from resolvix.core.telemetry.spans import snapshot
    from resolvix.core.tickets.sqlite_store import SqliteTicketStore

    return {"stage_latency": snapshot(), "insights": SqliteTicketStore().get_insights()}


@app.get("/readyz")
def readyz():
    try:
        get_pack(settings.DEFAULT_DOMAIN)
        return {"status": "ready"}
    except Exception as e:
        return {"status": "not ready", "error": str(e)}
