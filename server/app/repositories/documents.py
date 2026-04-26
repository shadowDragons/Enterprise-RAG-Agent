from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.models import Document


class DocumentRepository:
    def __init__(self, db: DBSession):
        self.db = db

    def list(self, knowledge_base_id: str | None = None) -> list[Document]:
        stmt = select(Document).order_by(Document.created_at.desc())
        if knowledge_base_id:
            stmt = stmt.where(Document.knowledge_base_id == knowledge_base_id)
        return list(self.db.scalars(stmt).all())

    def get(self, document_id: str) -> Document | None:
        stmt = select(Document).where(Document.document_id == document_id)
        return self.db.scalar(stmt)
