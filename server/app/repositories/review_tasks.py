from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.models import ReviewTask


class ReviewTaskRepository:
    def __init__(self, db: DBSession):
        self.db = db

    def list(
        self,
        *,
        status: str | None = None,
        session_id: str | None = None,
    ) -> list[ReviewTask]:
        stmt = select(ReviewTask).order_by(ReviewTask.created_at.desc())
        if status:
            stmt = stmt.where(ReviewTask.status == status)
        if session_id:
            stmt = stmt.where(ReviewTask.session_id == session_id)
        return list(self.db.scalars(stmt).all())

    def list_open(
        self,
        *,
        session_id: str | None = None,
    ) -> list[ReviewTask]:
        stmt = select(ReviewTask).where(
            ReviewTask.status.in_(("pending", "escalated"))
        )
        stmt = stmt.order_by(ReviewTask.created_at.desc())
        if session_id:
            stmt = stmt.where(ReviewTask.session_id == session_id)
        return list(self.db.scalars(stmt).all())

    def list_pending(self) -> list[ReviewTask]:
        stmt = (
            select(ReviewTask)
            .where(ReviewTask.status == "pending")
            .order_by(ReviewTask.created_at.asc())
        )
        return list(self.db.scalars(stmt).all())

    def get(self, review_id: str) -> ReviewTask | None:
        stmt = select(ReviewTask).where(ReviewTask.review_id == review_id)
        return self.db.scalar(stmt)

    def create(
        self,
        *,
        session_id: str,
        assistant_id: str,
        pending_message_id: str,
        question: str,
        review_reason: str,
        selected_knowledge_base_id: str,
        selected_kb_ids: list[str],
        citations: list[dict],
        retrieval_count: int,
        checkpoint_payload: dict,
        workflow_trace: list[dict],
    ) -> ReviewTask:
        now = datetime.now(timezone.utc)
        review_task = ReviewTask(
            review_id=str(uuid4()),
            session_id=session_id,
            assistant_id=assistant_id,
            pending_message_id=pending_message_id,
            status="pending",
            escalation_level=0,
            escalation_reason="",
            question=question,
            review_reason=review_reason,
            reviewer_note="",
            final_answer="",
            selected_knowledge_base_id=selected_knowledge_base_id,
            selected_kb_ids=selected_kb_ids,
            citations=citations,
            retrieval_count=retrieval_count,
            checkpoint_payload=checkpoint_payload,
            workflow_trace=workflow_trace,
            escalated_at=None,
            reviewed_at=None,
            created_at=now,
            updated_at=now,
        )
        self.db.add(review_task)
        self.db.commit()
        self.db.refresh(review_task)
        return review_task

    def mark_reviewed(
        self,
        review_task: ReviewTask,
        *,
        status: str,
        reviewer_note: str,
        final_answer: str,
        workflow_trace: list[dict],
    ) -> ReviewTask:
        review_task.status = status
        review_task.reviewer_note = reviewer_note
        review_task.final_answer = final_answer
        review_task.workflow_trace = workflow_trace
        review_task.reviewed_at = datetime.now(timezone.utc)
        self.db.add(review_task)
        self.db.commit()
        self.db.refresh(review_task)
        return review_task

    def mark_escalated(
        self,
        review_task: ReviewTask,
        *,
        escalation_reason: str,
        escalation_level: int = 1,
        escalated_at: datetime | None = None,
    ) -> ReviewTask:
        review_task.status = "escalated"
        review_task.escalation_level = max(1, int(escalation_level))
        review_task.escalation_reason = escalation_reason.strip()
        review_task.escalated_at = escalated_at or datetime.now(timezone.utc)
        self.db.add(review_task)
        self.db.commit()
        self.db.refresh(review_task)
        return review_task
