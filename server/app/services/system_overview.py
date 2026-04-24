from datetime import datetime, timezone

from fastapi import BackgroundTasks
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.config import get_settings
from app.core.task_sla import build_job_sla_snapshot, build_review_sla_snapshot
from app.integrations.langgraph_checkpointer import describe_workflow_checkpointer_backend
from app.models import Assistant, Job, KnowledgeBase, ReviewTask, Session
from app.schemas.system import (
    SystemAlert,
    SystemMaintenanceRequest,
    SystemMaintenanceResult,
    SystemOverview,
    SystemReadinessCheck,
    SystemReadinessSummary,
    SystemResourceCounts,
    SystemRuntimeOverview,
    SystemSessionCounts,
    SystemSummary,
    SystemTaskCounts,
)
from app.services.document_ingestion import (
    DocumentIngestionService,
    process_document_ingestion_job,
)
from app.services.review_tasks import ReviewTaskService


def _database_backend_label(database_url: str) -> str:
    normalized = database_url.strip().lower()
    if normalized.startswith("sqlite"):
        return "sqlite"
    if normalized.startswith("postgres"):
        return "postgres"
    return "other"


def _status_count_map(db: DBSession, status_column) -> dict[str, int]:
    rows = db.execute(
        select(status_column, func.count()).group_by(status_column)
    ).all()
    return {
        str(status or "").strip(): int(count)
        for status, count in rows
        if str(status or "").strip()
    }


def build_system_summary() -> SystemSummary:
    settings = get_settings()
    return SystemSummary(
        app_name=settings.app_name,
        version=settings.app_version,
        stage=settings.default_stage,
        frontend_stack="Vue 3 + Element Plus",
        backend_stack="FastAPI",
    )


def _build_system_alerts(
    *,
    runtime: SystemRuntimeOverview,
    sessions: SystemSessionCounts,
    tasks: SystemTaskCounts,
) -> list[SystemAlert]:
    alerts: list[SystemAlert] = []

    if tasks.reviews_escalated > 0:
        alerts.append(
            SystemAlert(
                level="critical",
                code="reviews_escalated",
                title="存在已升级审核任务",
                detail="人工审核已超时并自动升级，需要优先处理审核台中的升级项。",
                count=tasks.reviews_escalated,
            )
        )

    if tasks.jobs_failed > 0:
        alerts.append(
            SystemAlert(
                level="critical",
                code="jobs_failed",
                title="存在失败的文档任务",
                detail="任务中心中存在失败任务，建议尽快排查错误原因并执行重试。",
                count=tasks.jobs_failed,
            )
        )

    if tasks.jobs_breached > 0:
        alerts.append(
            SystemAlert(
                level="warning",
                code="jobs_breached",
                title="存在超时中的文档任务",
                detail="部分文档处理任务已超过 SLA，建议检查入库链路和依赖服务状态。",
                count=tasks.jobs_breached,
            )
        )

    if sessions.awaiting_clarification > 0:
        alerts.append(
            SystemAlert(
                level="info",
                code="sessions_waiting_clarification",
                title="存在待澄清会话",
                detail="当前有会话停留在澄清阶段，需关注意图识别与用户引导效果。",
                count=sessions.awaiting_clarification,
            )
        )

    if not runtime.auth_enabled:
        alerts.append(
            SystemAlert(
                level="warning",
                code="auth_disabled",
                title="鉴权已关闭",
                detail="当前环境未启用最小鉴权，仅适用于本地测试或自动化测试。",
            )
        )

    if runtime.workflow_checkpointer_backend != "postgres":
        alerts.append(
            SystemAlert(
                level="info",
                code="database_checkpointer",
                title="当前未使用官方 Postgres checkpointer",
                detail="当前环境仍使用内置数据库 checkpointer；正式部署前建议切换到官方 Postgres saver。",
            )
        )

    return alerts


def _build_readiness_summary(
    *,
    settings,
    runtime: SystemRuntimeOverview,
) -> SystemReadinessSummary:
    checks: list[SystemReadinessCheck] = []

    def append_check(status: str, code: str, title: str, detail: str) -> None:
        checks.append(
            SystemReadinessCheck(
                status=status,
                code=code,
                title=title,
                detail=detail,
            )
        )

    if runtime.auth_enabled and not settings.uses_default_auth_secret:
        append_check(
            "pass",
            "auth_secret",
            "鉴权密钥已替换",
            "当前 AUTH_SECRET_KEY 已脱离默认值，可用于正式环境鉴权签名。",
        )
    elif runtime.auth_enabled:
        append_check(
            "failed" if settings.is_production_like else "warning",
            "auth_secret",
            "鉴权密钥仍为默认值",
            "请在部署前替换 AUTH_SECRET_KEY，避免继续使用开发默认密钥。",
        )
    else:
        append_check(
            "failed" if settings.is_production_like else "warning",
            "auth_enabled",
            "鉴权未启用",
            "当前环境关闭了最小鉴权，正式部署前必须开启 AUTH_ENABLED=true。",
        )

    if runtime.database_backend == "postgres":
        append_check(
            "pass",
            "database_backend",
            "数据库后端已使用 Postgres",
            "当前 DATABASE_URL 指向 Postgres，符合生产部署基线。",
        )
    else:
        append_check(
            "failed" if settings.is_production_like else "warning",
            "database_backend",
            "数据库后端仍为 SQLite",
            "SQLite 仅适合开发和测试环境，正式部署前应切换到 Postgres。",
        )

    if settings.database_schema_strategy.strip().lower() == "migrate":
        append_check(
            "pass",
            "database_migration",
            "数据库迁移策略已锁定",
            "当前环境已启用 Alembic migration 作为数据库 schema 管理入口。",
        )
    else:
        append_check(
            "failed" if settings.is_production_like else "warning",
            "database_migration",
            "数据库迁移策略未锁定",
            "正式部署前建议将 DATABASE_SCHEMA_STRATEGY 设置为 migrate。",
        )

    if runtime.workflow_checkpointer_backend == "postgres":
        append_check(
            "pass",
            "workflow_checkpointer",
            "工作流 Checkpointer 已使用官方 Postgres saver",
            "当前环境满足 LangGraph 官方 Postgres checkpointer 基线。",
        )
    else:
        append_check(
            "failed" if settings.is_production_like else "warning",
            "workflow_checkpointer",
            "工作流 Checkpointer 仍未切到官方 Postgres saver",
            "正式部署前建议切换 WORKFLOW_CHECKPOINTER_BACKEND=postgres 并通过探针验证。",
        )

    if runtime.llm_provider in {"openai"}:
        append_check(
            "pass",
            "llm_provider",
            "LLM Provider 已锁定",
            f"当前生产回答链路已固定使用 {runtime.llm_provider}。",
        )
    else:
        append_check(
            "failed" if settings.is_production_like else "warning",
            "llm_provider",
            "LLM Provider 尚未锁定",
            "当前仍为 auto/local 等非最终模式，正式部署前应锁定真实 Provider。",
        )

    llm_allowed_models = [
        item.strip() for item in settings.llm_allowed_models if item.strip()
    ]
    if runtime.llm_model and (
        not llm_allowed_models or runtime.llm_model in llm_allowed_models
    ):
        append_check(
            "pass",
            "llm_model",
            "默认 LLM 模型已通过治理校验",
            f"当前默认模型 {runtime.llm_model} 位于允许列表内。",
        )
    else:
        append_check(
            "failed",
            "llm_model",
            "默认 LLM 模型未通过治理校验",
            f"当前默认模型 {runtime.llm_model or '未配置'} 不在允许列表内。",
        )

    if runtime.embedding_provider in {"openai"}:
        append_check(
            "pass",
            "embedding_provider",
            "Embedding Provider 已锁定",
            f"当前向量链路已固定使用 {runtime.embedding_provider}。",
        )
    else:
        append_check(
            "failed" if settings.is_production_like else "warning",
            "embedding_provider",
            "Embedding Provider 尚未锁定",
            "当前仍为 auto/local 等非最终模式，正式部署前应锁定真实 Provider。",
        )

    embedding_allowed_models = [
        item.strip() for item in settings.embedding_allowed_models if item.strip()
    ]
    if runtime.embedding_model and (
        not embedding_allowed_models
        or runtime.embedding_model in embedding_allowed_models
    ):
        append_check(
            "pass",
            "embedding_model",
            "默认 Embedding 模型已通过治理校验",
            f"当前默认向量模型 {runtime.embedding_model} 位于允许列表内。",
        )
    else:
        append_check(
            "failed",
            "embedding_model",
            "默认 Embedding 模型未通过治理校验",
            f"当前默认向量模型 {runtime.embedding_model or '未配置'} 不在允许列表内。",
        )

    if runtime.llm_provider in {"auto", "openai"} and (
        not settings.resolved_llm_api_base or not settings.resolved_llm_api_key
    ):
        append_check(
            "failed",
            "llm_credentials",
            "聊天模型连接配置不完整",
            "请检查 OPENAI_LLM_BASE_URL 与 OPENAI_LLM_API_KEY(_ENV_VAR) 是否已正确配置。",
        )
    else:
        append_check(
            "pass",
            "llm_credentials",
            "聊天模型连接配置完整",
            "当前聊天模型链路已具备必要的 Base URL 与 API key 配置。",
        )

    if runtime.embedding_provider in {"auto", "openai"} and not settings.resolved_embedding_api_key:
        append_check(
            "failed",
            "embedding_credentials",
            "Embedding 连接配置不完整",
            "请检查 OPENAI_EMBEDDING_API_KEY(_ENV_VAR) 是否已正确配置。",
        )
    else:
        append_check(
            "pass",
            "embedding_credentials",
            "Embedding 连接配置完整",
            "当前向量链路已具备必要的 API key 配置。",
        )

    failed = sum(1 for item in checks if item.status == "failed")
    warnings = sum(1 for item in checks if item.status == "warning")
    passed = sum(1 for item in checks if item.status == "pass")
    overall_status = "failed" if failed else ("warning" if warnings else "pass")
    return SystemReadinessSummary(
        overall_status=overall_status,
        passed=passed,
        warnings=warnings,
        failed=failed,
        checks=checks,
    )


def _resolve_health_status(alerts: list[SystemAlert]) -> str:
    if any(item.level == "critical" for item in alerts):
        return "critical"
    if any(item.level == "warning" for item in alerts):
        return "warning"
    return "normal"


class SystemOverviewService:
    def __init__(self, db: DBSession):
        self.db = db
        self.settings = get_settings()

    def build_overview(self) -> SystemOverview:
        ReviewTaskService(self.db).reconcile_overdue_reviews()

        workflow_checkpointer_backend, workflow_checkpointer_label = (
            describe_workflow_checkpointer_backend(settings=self.settings)
        )
        session_status_counts = _status_count_map(self.db, Session.status)
        job_status_counts = _status_count_map(self.db, Job.status)
        review_status_counts = _status_count_map(self.db, ReviewTask.status)

        jobs = list(self.db.scalars(select(Job)).all())
        reviews = list(self.db.scalars(select(ReviewTask)).all())

        job_warning_count = 0
        job_breached_count = 0
        for job in jobs:
            sla_status = str(build_job_sla_snapshot(job).get("status", "")).strip()
            if sla_status == "warning":
                job_warning_count += 1
            elif sla_status == "breached":
                job_breached_count += 1

        review_warning_count = 0
        review_breached_count = 0
        for review in reviews:
            sla_status = str(build_review_sla_snapshot(review).get("status", "")).strip()
            if sla_status == "warning":
                review_warning_count += 1
            elif sla_status == "breached":
                review_breached_count += 1

        runtime = SystemRuntimeOverview(
            app_env=self.settings.app_env,
            auth_enabled=bool(self.settings.auth_enabled),
            database_backend=_database_backend_label(self.settings.database_url),
            qdrant_backend="local" if self.settings.qdrant_use_local else "server",
            workflow_checkpointer_backend=workflow_checkpointer_backend,
            workflow_checkpointer_label=workflow_checkpointer_label,
            llm_provider=self.settings.llm_provider,
            llm_model=self.settings.llm_model,
            llm_allowed_models=list(self.settings.llm_allowed_models),
            embedding_provider=self.settings.embedding_provider,
            embedding_model=self.settings.embedding_model,
            embedding_allowed_models=list(self.settings.embedding_allowed_models),
        )
        resources = SystemResourceCounts(
            assistants_total=int(
                self.db.scalar(select(func.count()).select_from(Assistant)) or 0
            ),
            knowledge_bases_total=int(
                self.db.scalar(select(func.count()).select_from(KnowledgeBase)) or 0
            ),
            sessions_total=int(
                self.db.scalar(select(func.count()).select_from(Session)) or 0
            ),
        )
        session_counts = SystemSessionCounts(
            active=session_status_counts.get("active", 0),
            awaiting_clarification=session_status_counts.get("awaiting_clarification", 0),
            awaiting_review=session_status_counts.get("awaiting_review", 0),
        )
        task_counts = SystemTaskCounts(
            jobs_total=len(jobs),
            jobs_pending=job_status_counts.get("pending", 0),
            jobs_running=job_status_counts.get("running", 0),
            jobs_failed=job_status_counts.get("failed", 0),
            jobs_warning=job_warning_count,
            jobs_breached=job_breached_count,
            reviews_total=len(reviews),
            reviews_pending=review_status_counts.get("pending", 0),
            reviews_escalated=review_status_counts.get("escalated", 0),
            reviews_warning=review_warning_count,
            reviews_breached=review_breached_count,
        )
        alerts = _build_system_alerts(
            runtime=runtime,
            sessions=session_counts,
            tasks=task_counts,
        )
        readiness = _build_readiness_summary(
            settings=self.settings,
            runtime=runtime,
        )
        return SystemOverview(
            health_status=_resolve_health_status(alerts),
            summary=build_system_summary(),
            runtime=runtime,
            resources=resources,
            sessions=session_counts,
            tasks=task_counts,
            alerts=alerts,
            readiness=readiness,
        )

    def run_maintenance(
        self,
        payload: SystemMaintenanceRequest,
        background_tasks: BackgroundTasks,
    ) -> SystemMaintenanceResult:
        reconcile_count = 0
        retried_job_ids: list[str] = []
        skipped_job_ids: list[str] = []

        if payload.reconcile_overdue_reviews:
            reconcile_count = ReviewTaskService(self.db).reconcile_overdue_reviews()

        if payload.retry_failed_jobs:
            retry_limit = (
                payload.job_retry_limit or self.settings.system_job_batch_retry_limit
            )
            retried_items, skipped_job_ids = DocumentIngestionService(
                self.db
            ).retry_jobs(limit=retry_limit)

            for document, job in retried_items:
                retried_job_ids.append(job.job_id)
                background_tasks.add_task(
                    process_document_ingestion_job,
                    document.document_id,
                    job.job_id,
                )

        return SystemMaintenanceResult(
            executed_at=datetime.now(timezone.utc).isoformat(),
            reconcile_overdue_reviews_count=reconcile_count,
            retried_job_count=len(retried_job_ids),
            retried_job_ids=retried_job_ids,
            skipped_job_ids=skipped_job_ids,
        )
