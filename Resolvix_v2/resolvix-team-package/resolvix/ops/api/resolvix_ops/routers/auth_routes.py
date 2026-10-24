"""Authentication routes."""
from fastapi import APIRouter, Depends, HTTPException, status, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import verify_password, create_session_cookie
from ..audit import write_audit
from ..config import Settings
from ..deps import get_db, get_settings, get_principal, Principal
from ..orm import User

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """Login request (not in contracts, local model)."""
    email: str
    password: str


class LoginResponse(BaseModel):
    """Login response (not in contracts, local model)."""
    success: bool
    email: str


class MeResponse(BaseModel):
    """Current user response (additive extension)."""
    email: str
    role: str
    department: str | None


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    """Authenticate user and set session cookie."""
    # Find user
    user = db.query(User).filter(User.email == request.email).first()
    
    # Verify password
    if not user or not verify_password(request.password, user.password_hash):
        # Don't reveal whether email exists
        write_audit(db, request.email, "login_failed", "user", request.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # Create session cookie
    cookie_value = create_session_cookie(user.email, user.role, user.department, settings)
    response.set_cookie(
        key="resolvix_session",
        value=cookie_value,
        httponly=True,
        samesite="lax",
        secure=False,  # Set to True in production with HTTPS
        path="/"
    )
    
    write_audit(db, user.email, "login_success", "user", user.email)
    
    return LoginResponse(success=True, email=user.email)


@router.get("/me", response_model=MeResponse)
async def get_current_user(principal: Principal = Depends(get_principal)):
    """Get current user info (additive extension)."""
    if principal.kind != "user":
        raise HTTPException(status_code=401, detail="User session required")
    
    return MeResponse(
        email=principal.email or "",
        role=principal.role or "",
        department=principal.department
    )


@router.post("/logout")
async def logout(response: Response, principal: Principal = Depends(get_principal)):
    """Clear session cookie (additive extension)."""
    response.delete_cookie(key="resolvix_session", path="/")
    return {"success": True}
