"""Notification service seam for M3 SMS implementation."""
from sqlalchemy.orm import Session


class Notifier:
    """Notification service interface.
    
    Default implementation does nothing. M3 will provide the real SMS implementation.
    """
    
    def on_ticket_status_changed(
        self,
        db: Session,
        ticket,  # Ticket ORM object
        old_status: str | None,
        new_status: str,
        actor: str
    ):
        """Called when a ticket status changes.
        
        Args:
            db: Database session
            ticket: Ticket ORM object
            old_status: Previous status (None if newly created)
            new_status: New status
            actor: Actor who made the change (email or "service")
        """
        # Default: do nothing
        pass
