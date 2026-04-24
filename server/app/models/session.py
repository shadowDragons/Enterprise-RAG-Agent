from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Session(TimestampMixin, Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    assistant_id: Mapped[str] = mapped_column(
        ForeignKey("assistants.assistant_id"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), default="新会话", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    runtime_state: Mapped[str] = mapped_column(
        String(64),
        default="idle",
        nullable=False,
    )
    runtime_label: Mapped[str] = mapped_column(
        String(128),
        default="",
        nullable=False,
    )
    runtime_waiting_for: Mapped[str] = mapped_column(
        String(64),
        default="",
        nullable=False,
    )
    runtime_resume_strategy: Mapped[str] = mapped_column(
        String(32),
        default="none",
        nullable=False,
    )
    workflow_thread_id: Mapped[str] = mapped_column(
        String(128),
        default="",
        nullable=False,
    )
    runtime_reason: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )
    runtime_current_goal: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )
    runtime_resolved_question: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )
    runtime_pending_question: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )
    runtime_clarification_type: Mapped[str] = mapped_column(
        String(64),
        default="",
        nullable=False,
    )
    runtime_clarification_stage: Mapped[str] = mapped_column(
        String(64),
        default="",
        nullable=False,
    )
    runtime_clarification_expected_input: Mapped[str] = mapped_column(
        String(64),
        default="",
        nullable=False,
    )
    runtime_clarification_reason: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )
    runtime_context: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
