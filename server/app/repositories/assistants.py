from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Assistant
from app.schemas.assistant import AssistantCreate, AssistantUpdate


class AssistantRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self) -> list[Assistant]:
        stmt = select(Assistant).order_by(Assistant.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def get(self, assistant_id: str) -> Assistant | None:
        stmt = select(Assistant).where(Assistant.assistant_id == assistant_id)
        return self.db.scalar(stmt)

    def create(
        self,
        payload: AssistantCreate,
        *,
        normalized_kb_ids: list[str] | None = None,
    ) -> Assistant:
        assistant = Assistant(
            assistant_id=str(uuid4()),
            assistant_name=payload.assistant_name,
            description=payload.description,
            system_prompt=payload.system_prompt,
            default_model=payload.default_model,
            default_kb_ids=list(normalized_kb_ids or payload.default_kb_ids),
            tool_keys=payload.tool_keys,
            review_rules=[item.model_dump() for item in payload.review_rules],
            review_enabled=payload.review_enabled,
            version=1,
        )
        self.db.add(assistant)
        self.db.commit()
        self.db.refresh(assistant)
        return assistant

    def update(
        self,
        assistant: Assistant,
        payload: AssistantUpdate,
        *,
        normalized_kb_ids: list[str] | None = None,
    ) -> Assistant:
        assistant.assistant_name = payload.assistant_name
        assistant.description = payload.description
        assistant.system_prompt = payload.system_prompt
        assistant.default_model = payload.default_model
        assistant.default_kb_ids = list(normalized_kb_ids or payload.default_kb_ids)
        assistant.tool_keys = list(payload.tool_keys)
        assistant.review_rules = [item.model_dump() for item in payload.review_rules]
        assistant.review_enabled = payload.review_enabled
        assistant.version += 1
        self.db.add(assistant)
        self.db.commit()
        self.db.refresh(assistant)
        return assistant

    def restore_snapshot(
        self,
        assistant: Assistant,
        *,
        snapshot_payload: dict,
        normalized_kb_ids: list[str],
    ) -> Assistant:
        assistant.assistant_name = str(snapshot_payload.get("assistant_name", "")).strip()
        assistant.description = str(snapshot_payload.get("description", ""))
        assistant.system_prompt = str(snapshot_payload.get("system_prompt", ""))
        assistant.default_model = str(snapshot_payload.get("default_model", "gpt-4o"))
        assistant.default_kb_ids = list(normalized_kb_ids)
        assistant.tool_keys = list(snapshot_payload.get("tool_keys", []))
        assistant.review_rules = list(snapshot_payload.get("review_rules", []))
        assistant.review_enabled = bool(snapshot_payload.get("review_enabled", False))
        assistant.version += 1
        self.db.add(assistant)
        self.db.commit()
        self.db.refresh(assistant)
        return assistant
