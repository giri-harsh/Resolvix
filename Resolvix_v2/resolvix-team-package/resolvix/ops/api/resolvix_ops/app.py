"""FastAPI application factory."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from resolvix_contracts import DepartmentsConfig

from .config import Settings, load_settings
from .db import create_db_engine, get_session_factory
from .errors import validation_error_handler, http_exception_handler, general_exception_handler
from .orm import Base, TicketSeq
from .routers import health, auth_routes, config_routes
from .seed_users import seed_users_if_needed
from .services.notify import Notifier
from .sse import hub as sse_hub


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # Startup: capture event loop for SSE hub
    loop = asyncio.get_running_loop()
    sse_hub.set_loop(loop)
    
    yield
    
    # Shutdown: dispose engine
    app.state.engine.dispose()


def create_app(settings: Settings | None = None, notifier: Notifier | None = None) -> FastAPI:
    """Create and configure FastAPI application.
    
    Args:
        settings: Settings object (None = load from env)
        notifier: Notifier implementation (None = default no-op notifier)
    """
    
    if settings is None:
        settings = load_settings()
    
    if notifier is None:
        notifier = Notifier()
    
    # Create database engine
    engine = create_db_engine(settings)
    session_factory = get_session_factory(engine)
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    # Initialize ticket sequence if needed
    with session_factory() as db:
        seq = db.query(TicketSeq).first()
        if seq is None:
            seq = TicketSeq(id=1, next_num=1001)
            db.add(seq)
            db.commit()
    
    # Load and validate departments config
    departments_path = settings.resolve_path(settings.departments_file)
    with open(departments_path, "r", encoding="utf-8") as f:
        departments_raw = yaml.safe_load(f)
    departments_config = DepartmentsConfig.model_validate(departments_raw)
    
    # Seed users if enabled
    if settings.seed_users_on_startup:
        with session_factory() as db:
            departments_keys = {d.key for d in departments_config.departments}
            seed_users_if_needed(db, settings, departments_keys)
    
    # Create app
    app = FastAPI(
        title="Resolvix Ops API",
        version="1.0.0",
        description="Member C: Ops API, SMS service, Staff Dashboard backend",
        lifespan=lifespan
    )
    
    # Store state for dependencies
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.departments_config = departments_config
    app.state.notifier = notifier
    app.state.sse_hub = sse_hub
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Error handlers
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    from fastapi import HTTPException
    from starlette.exceptions import HTTPException as StarletteHTTPException
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
    
    # Include routers
    app.include_router(health.router)
    app.include_router(auth_routes.router)
    app.include_router(config_routes.router)
    
    # Import and include calls router
    from .routers import calls_routes, tickets_routes, sse_routes
    app.include_router(calls_routes.router)
    app.include_router(tickets_routes.router)
    app.include_router(sse_routes.router)
    
    return app


# For running with uvicorn directly
app = create_app()
