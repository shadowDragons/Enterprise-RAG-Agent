from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.models import Session
from app.schemas.session import SessionCreate


class SessionRepository:
    def __init__(self, db: DBSession):
        self.db = db

    def list(self, assistant_id: str | None = None) -> list[Session]:
        stmt = select(Session).order_by(Session.updated_at.desc())
        if assistant_id:
            stmt = stmt.where(Session.assistant_id == assistant_id)
        return list(self.db.scalars(stmt).all())

    def get(self, session_id: str) -> Session | None:
        stmt = select(Session).where(Session.session_id == session_id)
        return self.db.scalar(stmt)

    def create(self, payload: SessionCreate) -> Session:
        title = payload.title.strip() or "新会话"
        session = Session(
            session_id=str(uuid4()),
            assistant_id=payload.assistant_id,
            title=title,
            status="active",
            runtime_state="idle",
            runtime_label="",
            runtime_waiting_for="",
            runtime_resume_strategy="none",
            workflow_thread_id="",
            runtime_reason="",
            runtime_current_goal="",
            runtime_resolved_question="",
            runtime_pending_question="",
            runtime_clarification_type="",
            runtime_clarification_stage="",
            runtime_clarification_expected_input="",
            runtime_clarification_reason="",
            runtime_context={},
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def update_runtime(
        self,
        session_id: str,
        *,
        status: str,
        runtime_state: str = "",
        runtime_label: str = "",
        runtime_waiting_for: str = "",
        runtime_resume_strategy: str = "none",
        workflow_thread_id: str,
        runtime_reason: str = "",
        runtime_current_goal: str = "",
        runtime_resolved_question: str = "",
        runtime_pending_question: str = "",
        runtime_clarification_type: str = "",
        runtime_clarification_stage: str = "",
        runtime_clarification_expected_input: str = "",
        runtime_clarification_reason: str = "",
        runtime_context: dict | None = None,
    ) -> Session | None:
        session = self.get(session_id)
        if not session:
            return None

        session.status = status
        session.runtime_state = runtime_state.strip() or session.runtime_state
        session.runtime_label = runtime_label.strip()
        session.runtime_waiting_for = runtime_waiting_for.strip()
        session.runtime_resume_strategy = runtime_resume_strategy.strip() or "none"
        session.workflow_thread_id = workflow_thread_id.strip()
        session.runtime_reason = runtime_reason.strip()
        session.runtime_current_goal = runtime_current_goal.strip()
        session.runtime_resolved_question = runtime_resolved_question.strip()
        session.runtime_pending_question = runtime_pending_question.strip()
        session.runtime_clarification_type = runtime_clarification_type.strip()
        session.runtime_clarification_stage = runtime_clarification_stage.strip()
        session.runtime_clarification_expected_input = (
            runtime_clarification_expected_input.strip()
        )
        session.runtime_clarification_reason = runtime_clarification_reason.strip()
        session.runtime_context = dict(runtime_context or {})
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def update_status(self, session_id: str, *, status: str) -> Session | None:
        session = self.get(session_id)
        if not session:
            return None
        return self.update_runtime(
            session_id,
            status=status,
            runtime_state=session.runtime_state,
            runtime_label="",
            runtime_waiting_for="",
            runtime_resume_strategy="none",
            workflow_thread_id=session.workflow_thread_id,
            runtime_reason="",
            runtime_current_goal=session.runtime_current_goal,
            runtime_resolved_question=session.runtime_resolved_question,
            runtime_pending_question=session.runtime_pending_question,
            runtime_clarification_type=session.runtime_clarification_type,
            runtime_clarification_stage=session.runtime_clarification_stage,
            runtime_clarification_expected_input=session.runtime_clarification_expected_input,
            runtime_clarification_reason=session.runtime_clarification_reason,
            runtime_context={},
        )
