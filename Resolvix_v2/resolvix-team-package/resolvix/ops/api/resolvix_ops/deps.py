"""FastAPI dependencies for DI."""
from typing import Generator

from fastapi import Request, Header, Cookie, HTTPException, status
from sqlalchemy.orm import Session

from .auth import Principal, verify_service_key, decode_session_cookie
from .config import Settings


def get_settings(request: Request) -> Settings:
    """Get settings from app state."""
    return request.app.state.settings


def get_db(request: Request) -> Generator[Session, None, None]:
    """Get database session from app state."""
    session_factory = request.app.state.session_factory
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def get_principal(
    request: Request,
    x_service_key: str | None = Header(None, alias="X-Service-Key"),
    resolvix_session: str | None = Cookie(None)
) -> Principal:
    """Extract and verify authentication (service key or session cookie)."""
    settings = get_settings(request)
    
    # Try service key first
    if verify_service_key(x_service_key, settings):
        return Principal(kind="service")
    
    # Try session cookie
    if resolvix_session:
        session_data = decode_session_cookie(resolvix_session, settings)
        if session_data:
            return Principal(
                kind="user",
                email=session_data.get("email"),
                role=session_data.get("role"),
                department=session_data.get("department")
            )
    
    # No valid auth
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required"
    )


def require_admin(principal: Principal = None) -> Principal:
    """Require admin role. Use as Depends(require_admin) which chains get_principal."""
    from fastapi import Depends
    
    # This is called with principal from get_principal via Depends chain
    if principal is None:
        raise HTTPException(status_code=500, detail="Principal not injected")
    
    if principal.kind != "user" or principal.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return principal
