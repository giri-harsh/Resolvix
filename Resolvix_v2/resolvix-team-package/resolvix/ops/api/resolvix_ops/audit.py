"""Audit logging helpers."""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .orm import AuditLog


def write_audit(
    db: Session,
    actor: str,
    action: str,
    entity: str,
    entity_id: str,
    details: Optional[dict] = None
):
    """Write an audit log entry."""
    entry = AuditLog(
        actor=actor,
        action=action,
        entity=entity,
        entity_id=entity_id,
        details=details or {},
        at=datetime.utcnow()
    )
    db.add(entry)
    db.commit()
