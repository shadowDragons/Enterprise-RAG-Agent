from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.task_sla import build_job_sla_snapshot
from app.schemas.job import JobSummary, to_job_summary
from app.schemas.task_sla import TaskSlaSnapshot


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: str
    knowledge_base_id: str
    file_name: str
    mime_type: str
    status: str
    created_at: datetime
    updated_at: datetime


class DocumentUploadAccepted(BaseModel):
    document: DocumentSummary
    job: JobSummary


class DocumentDeleteResult(BaseModel):
    document_id: str
    knowledge_base_id: str
    deleted_chunk_count: int
    deleted_job_count: int


def to_document_summary(document) -> DocumentSummary:
    return DocumentSummary(
        document_id=document.document_id,
        knowledge_base_id=document.knowledge_base_id,
        file_name=document.file_name,
        mime_type=document.mime_type,
        status=document.status,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def to_document_upload_accepted(document, job) -> DocumentUploadAccepted:
    return DocumentUploadAccepted(
        document=to_document_summary(document),
        job=to_job_summary(
            job,
            target_type="document",
            target_name=document.file_name,
            knowledge_base_id=document.knowledge_base_id,
            retryable=False,
            target_status=document.status,
            sla=TaskSlaSnapshot(**build_job_sla_snapshot(job)),
        ),
    )
