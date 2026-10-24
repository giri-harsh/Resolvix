"""Configuration routes (departments, urgency rules)."""
from fastapi import APIRouter, Depends
from resolvix_contracts import DepartmentsConfig

from ..deps import get_principal, Principal, get_settings
from ..config import Settings

router = APIRouter(prefix="/v1", tags=["config"])


@router.get("/departments")
async def get_departments(
    principal: Principal = Depends(get_principal),
    settings: Settings = Depends(get_settings)
):
    """Get departments configuration."""
    # Load from app state (cached at startup)
    from fastapi import Request
    # We need access to request.app.state, so use a different approach
    # For now, reload from file (will optimize later)
    import yaml
    departments_path = settings.resolve_path(settings.departments_file)
    with open(departments_path, "r", encoding="utf-8") as f:
        departments_raw = yaml.safe_load(f)
    return DepartmentsConfig.model_validate(departments_raw)


@router.get("/urgency-rules")
async def get_urgency_rules(
    principal: Principal = Depends(get_principal),
    settings: Settings = Depends(get_settings)
):
    """Get urgency rules (read-only view)."""
    import yaml
    urgency_rules_path = settings.resolve_path(settings.urgency_rules_file)
    with open(urgency_rules_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
