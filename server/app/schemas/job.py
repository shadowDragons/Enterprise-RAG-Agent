from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.task_sla import TaskSlaSnapshot


class JobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    job_type: str
    target_id: str
    target_type: str | None = None
    target_name: str | None = None
    knowledge_base_id: str | None = None
    knowledge_base_name: str | None = None
    target_status: str | None = None
    retryable: bool = False
    status: str
    progress: float
    error_message: str
    sla: TaskSlaSnapshot
    created_at: datetime
    updated_at: datetime


class BatchRetryJobsRequest(BaseModel):
    job_ids: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=100)


class BatchRetryJobsResult(BaseModel):
    requested_count: int
    retried_count: int
    skipped_count: int
    retried_jobs: list[JobSummary] = Field(default_factory=list)
    skipped_job_ids: list[str] = Field(default_factory=list)


def to_job_summary(
    job,
    *,
    target_type: str | None = None,
    target_name: str | None = None,
    knowledge_base_id: str | None = None,
    knowledge_base_name: str | None = None,
    target_status: str | None = None,
    retryable: bool = False,
    sla: TaskSlaSnapshot,
) -> JobSummary:
    return JobSummary(
        job_id=job.job_id,
        job_type=job.job_type,
        target_id=job.target_id,
        target_type=target_type,
        target_name=target_name,
        knowledge_base_id=knowledge_base_id,
        knowledge_base_name=knowledge_base_name,
        target_status=target_status,
        retryable=retryable,
        status=job.status,
        progress=job.progress,
        error_message=job.error_message,
        sla=sla,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
