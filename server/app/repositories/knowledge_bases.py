from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeBase
from app.schemas.knowledge_base import KnowledgeBaseCreate


class KnowledgeBaseRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self) -> list[KnowledgeBase]:
        stmt = select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def get(self, knowledge_base_id: str) -> KnowledgeBase | None:
        stmt = select(KnowledgeBase).where(
            KnowledgeBase.knowledge_base_id == knowledge_base_id
        )
        return self.db.scalar(stmt)

    def create(self, payload: KnowledgeBaseCreate) -> KnowledgeBase:
        knowledge_base = KnowledgeBase(
            knowledge_base_id=str(uuid4()),
            knowledge_base_name=payload.knowledge_base_name,
            description=payload.description,
            default_retrieval_top_k=payload.default_retrieval_top_k,
        )
        self.db.add(knowledge_base)
        self.db.commit()
        self.db.refresh(knowledge_base)
        return knowledge_base
