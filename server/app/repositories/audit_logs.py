from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.models import AuditLog


class AuditLogRepository:
    def __init__(self, db: DBSession):
        self.db = db

    def create(
        self,
        *,
        assistant_id: str,
        session_id: str,
        review_id: str | None,
        workflow_thread_id: str,
        event_type: str,
        event_level: str,
        summary: str,
        detail_payload: dict | None = None,
    ) -> AuditLog:
        audit_log = AuditLog(
            audit_log_id=str(uuid4()),
            assistant_id=assistant_id,
            session_id=session_id,
            review_id=review_id,
            workflow_thread_id=workflow_thread_id.strip(),
            event_type=event_type,
            event_level=event_level,
            summary=summary.strip(),
            detail_payload=dict(detail_payload or {}),
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(audit_log)
        self.db.commit()
        self.db.refresh(audit_log)
        return audit_log

    def list(
        self,
        *,
        session_id: str | None = None,
        review_id: str | None = None,
        assistant_id: str | None = None,
        event_type: str | None = None,
        limit: int = 20,
    ) -> list[AuditLog]:
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
        if session_id:
            stmt = stmt.where(AuditLog.session_id == session_id)
        if review_id:
            stmt = stmt.where(AuditLog.review_id == review_id)
        if assistant_id:
            stmt = stmt.where(AuditLog.assistant_id == assistant_id)
        if event_type:
            stmt = stmt.where(AuditLog.event_type == event_type)
        stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())
