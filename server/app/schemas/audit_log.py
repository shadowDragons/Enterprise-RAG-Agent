from datetime import datetime

from pydantic import BaseModel, Field


class AuditLogEntry(BaseModel):
    audit_log_id: str
    assistant_id: str
    session_id: str
    review_id: str | None = None
    workflow_thread_id: str
    event_type: str
    event_level: str
    summary: str
    detail_payload: dict = Field(default_factory=dict)
    created_at: datetime


def to_audit_log_entry(audit_log) -> AuditLogEntry:
    return AuditLogEntry(
        audit_log_id=audit_log.audit_log_id,
        assistant_id=audit_log.assistant_id,
        session_id=audit_log.session_id,
        review_id=audit_log.review_id,
        workflow_thread_id=audit_log.workflow_thread_id,
        event_type=audit_log.event_type,
        event_level=audit_log.event_level,
        summary=audit_log.summary,
        detail_payload=dict(audit_log.detail_payload or {}),
        created_at=audit_log.created_at,
    )
