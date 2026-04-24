from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps.auth import require_permissions
from app.core.task_sla import build_job_sla_snapshot
from app.db.session import get_db
from app.models import Document, KnowledgeBase
from app.repositories.jobs import JobRepository
from app.schemas.job import JobSummary, to_job_summary
from app.schemas.job import BatchRetryJobsRequest, BatchRetryJobsResult
from app.schemas.task_sla import TaskSlaSnapshot
from app.services.document_ingestion import (
    DocumentIngestionService,
    DocumentIngestionStateError,
    process_document_ingestion_job,
)

router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
    dependencies=[Depends(require_permissions("job:read"))],
)


def _document_map(db: Session, document_ids: set[str]) -> dict[str, Document]:
    if not document_ids:
        return {}
    rows = db.scalars(
        select(Document).where(Document.document_id.in_(document_ids))
    ).all()
    return {item.document_id: item for item in rows}


def _knowledge_base_name_map(
    db: Session,
    knowledge_base_ids: set[str],
) -> dict[str, str]:
    if not knowledge_base_ids:
        return {}
    rows = db.execute(
        select(KnowledgeBase.knowledge_base_id, KnowledgeBase.knowledge_base_name).where(
            KnowledgeBase.knowledge_base_id.in_(knowledge_base_ids)
        )
    ).all()
    return {
        knowledge_base_id: knowledge_base_name
        for knowledge_base_id, knowledge_base_name in rows
    }


def _infer_job_target_type(job_type: str) -> str | None:
    if job_type == "document_ingestion":
        return "document"
    return None


def _to_job_summaries(db: Session, jobs) -> list[JobSummary]:
    document_ids = {
        item.target_id for item in jobs if _infer_job_target_type(item.job_type) == "document"
    }
    document_map = _document_map(db, document_ids)
    knowledge_base_name_map = _knowledge_base_name_map(
        db,
        {item.knowledge_base_id for item in document_map.values()},
    )

    result: list[JobSummary] = []
    for job in jobs:
        target_type = _infer_job_target_type(job.job_type)
        target_name = None
        knowledge_base_id = None
        knowledge_base_name = None
        target_status = None

        if target_type == "document":
            document = document_map.get(job.target_id)
            if document is not None:
                target_name = document.file_name
                knowledge_base_id = document.knowledge_base_id
                knowledge_base_name = knowledge_base_name_map.get(document.knowledge_base_id)
                target_status = document.status
        retryable = (
            target_type == "document"
            and job.status == "failed"
            and document_map.get(job.target_id) is not None
            and Path(document_map[job.target_id].file_path).exists()
        )
        sla = TaskSlaSnapshot(**build_job_sla_snapshot(job))

        result.append(
            to_job_summary(
                job,
                target_type=target_type,
                target_name=target_name,
                knowledge_base_id=knowledge_base_id,
                knowledge_base_name=knowledge_base_name,
                target_status=target_status,
                retryable=retryable,
                sla=sla,
            )
        )
    return result


@router.get("", response_model=list[JobSummary])
async def list_jobs(
    job_type: str | None = Query(default=None),
    job_status: str | None = Query(default=None, alias="status"),
    sla_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[JobSummary]:
    repository = JobRepository(db)
    jobs = repository.list(job_type=job_type, status=job_status)
    summaries = _to_job_summaries(db, jobs)
    if sla_status:
        summaries = [item for item in summaries if item.sla.status == sla_status]
    return summaries


@router.get("/{job_id}", response_model=JobSummary)
async def get_job(
    job_id: str,
    db: Session = Depends(get_db),
) -> JobSummary:
    repository = JobRepository(db)
    job = repository.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在。",
        )
    return _to_job_summaries(db, [job])[0]


@router.post(
    "/{job_id}/retry",
    response_model=JobSummary,
    dependencies=[Depends(require_permissions("job:write"))],
)
async def retry_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobSummary:
    service = DocumentIngestionService(db)
    try:
        document, job = service.retry_job(job_id)
    except DocumentIngestionStateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    background_tasks.add_task(
        process_document_ingestion_job,
        document.document_id,
        job.job_id,
    )
    return _to_job_summaries(db, [job])[0]


@router.post(
    "/retry-batch",
    response_model=BatchRetryJobsResult,
    dependencies=[Depends(require_permissions("job:write"))],
)
async def retry_jobs_batch(
    payload: BatchRetryJobsRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> BatchRetryJobsResult:
    service = DocumentIngestionService(db)
    try:
        retried_items, skipped_job_ids = service.retry_jobs(
            job_ids=payload.job_ids,
            limit=payload.limit,
        )
    except DocumentIngestionStateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    for document, job in retried_items:
        background_tasks.add_task(
            process_document_ingestion_job,
            document.document_id,
            job.job_id,
        )

    retried_jobs = _to_job_summaries(db, [job for _, job in retried_items])
    requested_count = (
        min(len(payload.job_ids), payload.limit) if payload.job_ids else payload.limit
    )
    return BatchRetryJobsResult(
        requested_count=requested_count,
        retried_count=len(retried_jobs),
        skipped_count=len(skipped_job_ids),
        retried_jobs=retried_jobs,
        skipped_job_ids=skipped_job_ids,
    )
