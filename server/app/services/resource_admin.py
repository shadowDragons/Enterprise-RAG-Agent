from pathlib import Path
from shutil import rmtree

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.integrations.qdrant_store import QdrantChunkStore
from app.models import (
    Assistant,
    AssistantVersion,
    AuditLog,
    Document,
    DocumentChunk,
    Job,
    KnowledgeBase,
    Message,
    ReviewTask,
    Session as ChatSession,
    WorkflowCheckpoint,
)
from app.services.assistant_configs import build_assistant_snapshot_payload


class ResourceAdminStateError(RuntimeError):
    def __init__(self, detail: str, *, status_code: int) -> None:
        super().__init__(detail)
        self.status_code = status_code


class ResourceAdminService:
    def __init__(self, db) -> None:
        self.db = db
        self.settings = get_settings()
        self.qdrant_store = QdrantChunkStore()

    def update_knowledge_base(self, knowledge_base_id: str, payload):
        knowledge_base = self._require_knowledge_base(knowledge_base_id)
        knowledge_base.knowledge_base_name = payload.knowledge_base_name
        knowledge_base.description = payload.description
        knowledge_base.default_retrieval_top_k = payload.default_retrieval_top_k
        self.db.add(knowledge_base)
        self.db.commit()
        self.db.refresh(knowledge_base)
        return knowledge_base

    def delete_document(self, document_id: str) -> dict:
        document = self.db.scalar(
            select(Document).where(Document.document_id == document_id)
        )
        if document is None:
            raise ResourceAdminStateError("文档不存在。", status_code=404)

        chunk_ids = list(
            self.db.scalars(
                select(DocumentChunk.chunk_id).where(
                    DocumentChunk.document_id == document.document_id
                )
            ).all()
        )
        deleted_job_count = self.db.query(Job).filter(Job.target_id == document_id).count()

        self.qdrant_store.delete_chunk_ids(chunk_ids)
        self.db.execute(delete(Job).where(Job.target_id == document.document_id))
        self.db.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document.document_id)
        )
        self.db.execute(delete(Document).where(Document.document_id == document.document_id))
        self.db.commit()

        self._unlink_file(Path(document.file_path))
        self._cleanup_empty_parent_dirs(Path(document.file_path).parent)
        return {
            "document_id": document.document_id,
            "knowledge_base_id": document.knowledge_base_id,
            "deleted_chunk_count": len(chunk_ids),
            "deleted_job_count": deleted_job_count,
        }

    def delete_knowledge_base(self, knowledge_base_id: str) -> dict:
        knowledge_base = self._require_knowledge_base(knowledge_base_id)
        documents = list(
            self.db.scalars(
                select(Document).where(Document.knowledge_base_id == knowledge_base_id)
            ).all()
        )
        document_ids = [item.document_id for item in documents]
        file_paths = [Path(item.file_path) for item in documents]
        chunk_ids = list(
            self.db.scalars(
                select(DocumentChunk.chunk_id).where(
                    DocumentChunk.knowledge_base_id == knowledge_base_id
                )
            ).all()
        )
        deleted_job_count = 0
        if document_ids:
            deleted_job_count = (
                self.db.query(Job).filter(Job.target_id.in_(document_ids)).count()
            )

        affected_assistants = list(self.db.scalars(select(Assistant)).all())
        unbound_assistant_count = 0
        for assistant in affected_assistants:
            if knowledge_base_id not in list(assistant.default_kb_ids or []):
                continue
            assistant.default_kb_ids = [
                item for item in list(assistant.default_kb_ids or []) if item != knowledge_base_id
            ]
            assistant.version += 1
            self.db.add(assistant)
            self.db.add(
                AssistantVersion(
                    assistant_version_id=self._new_uuid(),
                    assistant_id=assistant.assistant_id,
                    version=assistant.version,
                    change_note=f"因知识库“{knowledge_base.knowledge_base_name}”删除自动解绑",
                    snapshot_payload=build_assistant_snapshot_payload(assistant),
                )
            )
            unbound_assistant_count += 1

        self.qdrant_store.delete_chunk_ids(chunk_ids)
        if document_ids:
            self.db.execute(delete(Job).where(Job.target_id.in_(document_ids)))
        self.db.execute(
            delete(DocumentChunk).where(DocumentChunk.knowledge_base_id == knowledge_base_id)
        )
        self.db.execute(delete(Document).where(Document.knowledge_base_id == knowledge_base_id))
        self.db.execute(
            delete(KnowledgeBase).where(
                KnowledgeBase.knowledge_base_id == knowledge_base_id
            )
        )
        self.db.commit()

        for file_path in file_paths:
            self._unlink_file(file_path)
        rmtree(Path(self.settings.storage_root) / "uploads" / knowledge_base_id, ignore_errors=True)
        return {
            "knowledge_base_id": knowledge_base_id,
            "deleted_document_count": len(document_ids),
            "deleted_chunk_count": len(chunk_ids),
            "deleted_job_count": deleted_job_count,
            "unbound_assistant_count": unbound_assistant_count,
        }

    def delete_assistant(self, assistant_id: str) -> dict:
        assistant = self.db.scalar(
            select(Assistant).where(Assistant.assistant_id == assistant_id)
        )
        if assistant is None:
            raise ResourceAdminStateError("助理不存在。", status_code=404)

        sessions = list(
            self.db.scalars(
                select(ChatSession).where(ChatSession.assistant_id == assistant_id)
            ).all()
        )
        session_ids = [item.session_id for item in sessions]
        review_tasks = list(
            self.db.scalars(
                select(ReviewTask).where(ReviewTask.assistant_id == assistant_id)
            ).all()
        )
        review_ids = [item.review_id for item in review_tasks]
        thread_ids = {
            item.workflow_thread_id.strip()
            for item in sessions
            if item.workflow_thread_id.strip()
        }
        thread_ids.update(
            str((item.checkpoint_payload or {}).get("workflow_thread_id", "")).strip()
            for item in review_tasks
            if str((item.checkpoint_payload or {}).get("workflow_thread_id", "")).strip()
        )

        deleted_audit_log_count = (
            self.db.query(AuditLog).filter(AuditLog.assistant_id == assistant_id).count()
        )
        deleted_review_count = len(review_ids)
        deleted_session_count = len(session_ids)
        deleted_checkpoint_count = 0
        if thread_ids:
            deleted_checkpoint_count = (
                self.db.query(WorkflowCheckpoint)
                .filter(WorkflowCheckpoint.thread_id.in_(list(thread_ids)))
                .count()
            )

        self.db.execute(delete(AuditLog).where(AuditLog.assistant_id == assistant_id))
        self.db.execute(delete(ReviewTask).where(ReviewTask.assistant_id == assistant_id))
        if session_ids:
            self.db.execute(delete(Message).where(Message.session_id.in_(session_ids)))
        if thread_ids:
            self.db.execute(
                delete(WorkflowCheckpoint).where(
                    WorkflowCheckpoint.thread_id.in_(list(thread_ids))
                )
            )
        self.db.execute(delete(ChatSession).where(ChatSession.assistant_id == assistant_id))
        self.db.execute(
            delete(AssistantVersion).where(AssistantVersion.assistant_id == assistant_id)
        )
        self.db.execute(delete(Assistant).where(Assistant.assistant_id == assistant_id))
        self.db.commit()

        return {
            "assistant_id": assistant_id,
            "deleted_session_count": deleted_session_count,
            "deleted_review_count": deleted_review_count,
            "deleted_audit_log_count": deleted_audit_log_count,
            "deleted_checkpoint_count": deleted_checkpoint_count,
        }

    def delete_session(self, session_id: str) -> dict:
        session = self.db.scalar(
            select(ChatSession).where(ChatSession.session_id == session_id)
        )
        if session is None:
            raise ResourceAdminStateError("会话不存在。", status_code=404)

        review_tasks = list(
            self.db.scalars(
                select(ReviewTask).where(ReviewTask.session_id == session_id)
            ).all()
        )
        review_ids = [item.review_id for item in review_tasks]
        thread_ids = {session.workflow_thread_id.strip()} if session.workflow_thread_id.strip() else set()
        thread_ids.update(
            str((item.checkpoint_payload or {}).get("workflow_thread_id", "")).strip()
            for item in review_tasks
            if str((item.checkpoint_payload or {}).get("workflow_thread_id", "")).strip()
        )

        deleted_message_count = (
            self.db.query(Message).filter(Message.session_id == session_id).count()
        )
        deleted_review_count = len(review_ids)
        deleted_audit_log_count = (
            self.db.query(AuditLog).filter(AuditLog.session_id == session_id).count()
        )
        deleted_checkpoint_count = 0
        if thread_ids:
            deleted_checkpoint_count = (
                self.db.query(WorkflowCheckpoint)
                .filter(WorkflowCheckpoint.thread_id.in_(list(thread_ids)))
                .count()
            )

        self.db.execute(delete(AuditLog).where(AuditLog.session_id == session_id))
        self.db.execute(delete(ReviewTask).where(ReviewTask.session_id == session_id))
        self.db.execute(delete(Message).where(Message.session_id == session_id))
        if thread_ids:
            self.db.execute(
                delete(WorkflowCheckpoint).where(
                    WorkflowCheckpoint.thread_id.in_(list(thread_ids))
                )
            )
        self.db.execute(delete(ChatSession).where(ChatSession.session_id == session_id))
        self.db.commit()

        return {
            "session_id": session_id,
            "assistant_id": session.assistant_id,
            "deleted_message_count": deleted_message_count,
            "deleted_review_count": deleted_review_count,
            "deleted_audit_log_count": deleted_audit_log_count,
            "deleted_checkpoint_count": deleted_checkpoint_count,
        }

    def _require_knowledge_base(self, knowledge_base_id: str):
        knowledge_base = self.db.scalar(
            select(KnowledgeBase).where(
                KnowledgeBase.knowledge_base_id == knowledge_base_id
            )
        )
        if knowledge_base is None:
            raise ResourceAdminStateError("知识库不存在。", status_code=404)
        return knowledge_base

    def _unlink_file(self, file_path: Path) -> None:
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            return

    def _cleanup_empty_parent_dirs(self, directory: Path) -> None:
        current = directory
        uploads_root = Path(self.settings.storage_root) / "uploads"
        while current != uploads_root.parent and current.exists():
            try:
                current.rmdir()
            except OSError:
                break
            if current == uploads_root:
                break
            current = current.parent

    def _new_uuid(self) -> str:
        from uuid import uuid4

        return str(uuid4())
