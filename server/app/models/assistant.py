from sqlalchemy import Boolean, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Assistant(TimestampMixin, Base):
    __tablename__ = "assistants"

    assistant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    assistant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    default_model: Mapped[str] = mapped_column(String(255), default="gpt-4o", nullable=False)
    default_kb_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    tool_keys: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    review_rules: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    review_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    multi_agent_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
