from pydantic import BaseModel, Field


class SystemSummary(BaseModel):
    app_name: str
    version: str
    stage: str
    frontend_stack: str
    backend_stack: str


class SystemRuntimeOverview(BaseModel):
    app_env: str
    auth_enabled: bool
    database_backend: str
    qdrant_backend: str
    workflow_checkpointer_backend: str
    workflow_checkpointer_label: str
    llm_provider: str
    llm_model: str
    llm_allowed_models: list[str] = Field(default_factory=list)
    embedding_provider: str
    embedding_model: str
    embedding_allowed_models: list[str] = Field(default_factory=list)


class SystemResourceCounts(BaseModel):
    assistants_total: int
    knowledge_bases_total: int
    sessions_total: int


class SystemSessionCounts(BaseModel):
    active: int = 0
    awaiting_clarification: int = 0
    awaiting_review: int = 0


class SystemTaskCounts(BaseModel):
    jobs_total: int
    jobs_pending: int = 0
    jobs_running: int = 0
    jobs_failed: int = 0
    jobs_warning: int = 0
    jobs_breached: int = 0
    reviews_total: int
    reviews_pending: int = 0
    reviews_escalated: int = 0
    reviews_warning: int = 0
    reviews_breached: int = 0


class SystemAlert(BaseModel):
    level: str
    code: str
    title: str
    detail: str
    count: int | None = None


class SystemReadinessCheck(BaseModel):
    status: str
    code: str
    title: str
    detail: str


class SystemReadinessSummary(BaseModel):
    overall_status: str
    passed: int = 0
    warnings: int = 0
    failed: int = 0
    checks: list[SystemReadinessCheck] = Field(default_factory=list)


class SystemMaintenanceRequest(BaseModel):
    reconcile_overdue_reviews: bool = True
    retry_failed_jobs: bool = False
    job_retry_limit: int | None = Field(default=None, ge=1, le=100)


class SystemMaintenanceResult(BaseModel):
    executed_at: str
    reconcile_overdue_reviews_count: int = 0
    retried_job_count: int = 0
    retried_job_ids: list[str] = Field(default_factory=list)
    skipped_job_ids: list[str] = Field(default_factory=list)


class SystemOverview(BaseModel):
    health_status: str
    summary: SystemSummary
    runtime: SystemRuntimeOverview
    resources: SystemResourceCounts
    sessions: SystemSessionCounts
    tasks: SystemTaskCounts
    alerts: list[SystemAlert] = Field(default_factory=list)
    readiness: SystemReadinessSummary
