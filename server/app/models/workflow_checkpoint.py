from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class WorkflowCheckpoint(TimestampMixin, Base):
    __tablename__ = "workflow_checkpoints"

    thread_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
        default="",
    )
    checkpoint_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    parent_checkpoint_id: Mapped[str | None] = mapped_column(String(128))
    checkpoint_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    metadata_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    pending_writes_payload: Mapped[list[dict]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
