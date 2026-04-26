from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

from app.models import WorkflowCheckpoint


class WorkflowCheckpointRepository:
    def __init__(self, db: DBSession):
        self.db = db

    def get(
        self,
        *,
        thread_id: str,
        checkpoint_ns: str = "",
        checkpoint_id: str | None = None,
    ) -> WorkflowCheckpoint | None:
        stmt = select(WorkflowCheckpoint).where(
            WorkflowCheckpoint.thread_id == thread_id,
            WorkflowCheckpoint.checkpoint_ns == checkpoint_ns,
        )
        if checkpoint_id:
            stmt = stmt.where(WorkflowCheckpoint.checkpoint_id == checkpoint_id)
        else:
            stmt = stmt.order_by(WorkflowCheckpoint.checkpoint_id.desc()).limit(1)
        return self.db.scalar(stmt)

    def list(
        self,
        *,
        thread_id: str | None = None,
        checkpoint_ns: str | None = None,
        before_checkpoint_id: str | None = None,
        limit: int | None = None,
    ) -> list[WorkflowCheckpoint]:
        stmt = select(WorkflowCheckpoint).order_by(
            WorkflowCheckpoint.checkpoint_id.desc()
        )
        if thread_id is not None:
            stmt = stmt.where(WorkflowCheckpoint.thread_id == thread_id)
        if checkpoint_ns is not None:
            stmt = stmt.where(WorkflowCheckpoint.checkpoint_ns == checkpoint_ns)
        if before_checkpoint_id:
            stmt = stmt.where(WorkflowCheckpoint.checkpoint_id < before_checkpoint_id)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def save(
        self,
        *,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
        parent_checkpoint_id: str | None,
        checkpoint_payload: dict,
        metadata_payload: dict,
    ) -> WorkflowCheckpoint:
        checkpoint = self.get(
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            checkpoint_id=checkpoint_id,
        )
        now = datetime.now(timezone.utc)
        if checkpoint is None:
            checkpoint = WorkflowCheckpoint(
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=checkpoint_id,
                parent_checkpoint_id=parent_checkpoint_id,
                checkpoint_payload=checkpoint_payload,
                metadata_payload=metadata_payload,
                pending_writes_payload=[],
                created_at=now,
                updated_at=now,
            )
        else:
            checkpoint.parent_checkpoint_id = parent_checkpoint_id
            checkpoint.checkpoint_payload = checkpoint_payload
            checkpoint.metadata_payload = metadata_payload
            checkpoint.updated_at = now

        self.db.add(checkpoint)
        self.db.commit()
        self.db.refresh(checkpoint)
        return checkpoint

    def update_pending_writes(
        self,
        *,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
        pending_writes_payload: list[dict],
    ) -> WorkflowCheckpoint | None:
        checkpoint = self.get(
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            checkpoint_id=checkpoint_id,
        )
        if checkpoint is None:
            return None

        checkpoint.pending_writes_payload = pending_writes_payload
        checkpoint.updated_at = datetime.now(timezone.utc)
        self.db.add(checkpoint)
        self.db.commit()
        self.db.refresh(checkpoint)
        return checkpoint

    def delete_thread(self, *, thread_id: str) -> None:
        self.db.execute(
            delete(WorkflowCheckpoint).where(WorkflowCheckpoint.thread_id == thread_id)
        )
        self.db.commit()
