from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.models import Message


class MessageRepository:
    def __init__(self, db: DBSession):
        self.db = db

    def list(self, session_id: str) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.asc(), Message.message_id.asc())
        )
        return list(self.db.scalars(stmt).all())

    def list_recent(self, session_id: str, limit: int) -> list[Message]:
        if limit <= 0:
            return []
        return self.list(session_id=session_id)[-limit:]

    def create(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: list[dict] | None = None,
    ) -> Message:
        now = datetime.now(timezone.utc)
        message = Message(
            message_id=str(uuid4()),
            session_id=session_id,
            role=role,
            content=content,
            citations=citations or [],
            created_at=now,
            updated_at=now,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def update(
        self,
        message_id: str,
        *,
        content: str,
        citations: list[dict] | None = None,
    ) -> Message | None:
        message = self.db.get(Message, message_id)
        if not message:
            return None

        message.content = content
        if citations is not None:
            message.citations = citations
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message
