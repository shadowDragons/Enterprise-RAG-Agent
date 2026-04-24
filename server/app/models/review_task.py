from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ReviewTask(TimestampMixin, Base):
    __tablename__ = "review_tasks"

    review_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.session_id"),
        nullable=False,
    )
    assistant_id: Mapped[str] = mapped_column(
        ForeignKey("assistants.assistant_id"),
        nullable=False,
    )
    pending_message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.message_id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    escalation_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    review_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reviewer_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    final_answer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    selected_knowledge_base_id: Mapped[str] = mapped_column(
        String(36),
        default="",
        nullable=False,
    )
    selected_kb_ids: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    citations: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    retrieval_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checkpoint_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    workflow_trace: Mapped[list[dict]] = mapped_column(
        JSON, default=list, nullable=False
    )
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
