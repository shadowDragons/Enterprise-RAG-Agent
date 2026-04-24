from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.chat import ChatCitation


class MessageSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: str
    session_id: str
    role: str
    content: str
    citations: list[ChatCitation]
    created_at: datetime
    updated_at: datetime


def to_message_summary(message) -> MessageSummary:
    return MessageSummary(
        message_id=message.message_id,
        session_id=message.session_id,
        role=message.role,
        content=message.content,
        citations=message.citations,
        created_at=message.created_at,
        updated_at=message.updated_at,
    )
