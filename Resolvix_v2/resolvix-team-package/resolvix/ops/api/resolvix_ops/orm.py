"""SQLAlchemy ORM models."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime, JSON, Index, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Call(Base):
    __tablename__ = "calls"
    
    call_id = Column(String, primary_key=True)
    channel = Column(String, nullable=False)
    caller_number = Column(String, nullable=True)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    kb_version = Column(String, nullable=False)
    lang = Column(String, nullable=False, default="hinglish")
    outcome = Column(String, nullable=True)
    ai_resolved = Column(Boolean, nullable=True)
    turns_count = Column(Integer, default=0)


class Turn(Base):
    __tablename__ = "turns"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    call_id = Column(String, ForeignKey("calls.call_id"), nullable=False)
    turn_index = Column(Integer, nullable=False)
    summary_json = Column(JSON, nullable=False)  # TurnSummary as JSON
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint("call_id", "turn_index", name="uq_turn_call_index"),
        Index("ix_turn_call_id", "call_id"),
    )


class TicketSeq(Base):
    __tablename__ = "ticket_seq"
    
    id = Column(Integer, primary_key=True, default=1)  # single row
    next_num = Column(Integer, nullable=False, default=1001)


class Ticket(Base):
    __tablename__ = "tickets"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(String, unique=True, nullable=False, index=True)
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    call_id = Column(String, ForeignKey("calls.call_id"), nullable=True)
    type = Column(String, nullable=False)
    priority = Column(String, nullable=False, index=True)
    priority_reason = Column(Text, nullable=False)
    rule_id = Column(String, nullable=True)  # Urgency rule that triggered this priority
    department = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="open", index=True)
    summary = Column(Text, nullable=False)
    collected_fields = Column(JSON, default=dict)
    caller_number = Column(String, nullable=True, index=True)
    callback_number = Column(String, nullable=True)
    callback_requested = Column(Boolean, default=False)
    transcript_excerpt = Column(Text, default="")
    brief = Column(Text, default="")
    assignee = Column(String, nullable=True)
    notes = Column(JSON, default=list)  # list of strings
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


class TicketEvent(Base):
    __tablename__ = "ticket_events"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(String, ForeignKey("tickets.ticket_id"), nullable=False, index=True)
    kind = Column(String, nullable=False)
    payload = Column(JSON, default=dict)
    actor = Column(String, default="system")
    at = Column(DateTime, nullable=False, default=datetime.utcnow)


class SmsMessage(Base):
    __tablename__ = "sms_messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    message_id = Column(String, nullable=False)
    to_number = Column(String, nullable=False)
    template_id = Column(String, nullable=False)
    vars_json = Column(JSON, default=dict)
    consent = Column(String, nullable=False)
    call_id = Column(String, nullable=True)
    ticket_id = Column(String, nullable=True)
    status = Column(String, nullable=False)
    mode = Column(String, nullable=False)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Gap(Base):
    __tablename__ = "gaps"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(Text, nullable=False)
    lang = Column(String, nullable=False)
    department_guess = Column(String, nullable=True)
    call_id = Column(String, nullable=True)
    ticket_id = Column(String, nullable=True)
    cluster_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class GapCluster(Base):
    __tablename__ = "gap_clusters"
    
    cluster_id = Column(String, primary_key=True)
    label = Column(String, nullable=False)
    department = Column(String, nullable=True)
    count = Column(Integer, default=1)
    examples = Column(JSON, default=list)
    last_seen = Column(DateTime, nullable=False, default=datetime.utcnow)
    status = Column(String, default="new")


class KBEntryDB(Base):
    __tablename__ = "kb_entries"
    
    id = Column(String, primary_key=True)  # KB entry ID like FEE-001
    status = Column(String, nullable=False, default="draft", index=True)
    body_json = Column(JSON, nullable=False)  # full KBEntry as JSON
    flagged = Column(Boolean, default=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String, nullable=True)


class KBPublish(Base):
    __tablename__ = "kb_publishes"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    kb_version = Column(String, nullable=False, unique=True, index=True)
    info_json = Column(JSON, nullable=False)  # KBVersionInfo as JSON
    actor = Column(String, nullable=False)
    at = Column(DateTime, nullable=False, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "admin" or "staff"
    department = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    actor = Column(String, nullable=False)
    action = Column(String, nullable=False)
    entity = Column(String, nullable=False)  # "ticket", "kb", "call", etc.
    entity_id = Column(String, nullable=False)
    details = Column(JSON, default=dict)
    at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
