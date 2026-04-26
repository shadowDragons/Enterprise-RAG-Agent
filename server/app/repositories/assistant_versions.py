from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AssistantVersion


class AssistantVersionRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self, assistant_id: str) -> list[AssistantVersion]:
        stmt = (
            select(AssistantVersion)
            .where(AssistantVersion.assistant_id == assistant_id)
            .order_by(AssistantVersion.version.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get(self, assistant_id: str, version: int) -> AssistantVersion | None:
        stmt = select(AssistantVersion).where(
            AssistantVersion.assistant_id == assistant_id,
            AssistantVersion.version == version,
        )
        return self.db.scalar(stmt)

    def create(
        self,
        *,
        assistant_id: str,
        version: int,
        change_note: str,
        snapshot_payload: dict,
    ) -> AssistantVersion:
        assistant_version = AssistantVersion(
            assistant_version_id=str(uuid4()),
            assistant_id=assistant_id,
            version=version,
            change_note=change_note.strip(),
            snapshot_payload=dict(snapshot_payload),
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(assistant_version)
        self.db.commit()
        self.db.refresh(assistant_version)
        return assistant_version
