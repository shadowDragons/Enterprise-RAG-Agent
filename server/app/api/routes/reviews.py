from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps.auth import require_permissions
from app.core.task_sla import build_review_sla_snapshot
from app.db.session import get_db
from app.models import Assistant, Session as ChatSession
from app.repositories.audit_logs import AuditLogRepository
from app.repositories.review_tasks import ReviewTaskRepository
from app.schemas.audit_log import AuditLogEntry, to_audit_log_entry
from app.schemas.review_task import (
    ReviewApproveRequest,
    ReviewRejectRequest,
    ReviewTaskDetail,
    ReviewTaskSummary,
    to_review_task_detail,
    to_review_task_summary,
)
from app.schemas.task_sla import TaskSlaSnapshot
from app.services.review_tasks import ReviewTaskService, ReviewTaskStateError

router = APIRouter(
    prefix="/reviews",
    tags=["reviews"],
    dependencies=[Depends(require_permissions("review:read"))],
)


def _assistant_name_map(
    db: Session,
    assistant_ids: set[str] | None = None,
) -> dict[str, str]:
    stmt = select(Assistant.assistant_id, Assistant.assistant_name)
    if assistant_ids:
        stmt = stmt.where(Assistant.assistant_id.in_(assistant_ids))
    return {
        assistant_id: assistant_name
        for assistant_id, assistant_name in db.execute(stmt).all()
    }


def _session_title_map(
    db: Session,
    session_ids: set[str] | None = None,
) -> dict[str, str]:
    stmt = select(ChatSession.session_id, ChatSession.title)
    if session_ids:
        stmt = stmt.where(ChatSession.session_id.in_(session_ids))
    return {session_id: title for session_id, title in db.execute(stmt).all()}


@router.get("", response_model=list[ReviewTaskSummary])
async def list_review_tasks(
    review_status: str | None = Query(default=None, alias="status"),
    session_id: str | None = Query(default=None),
    sla_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ReviewTaskSummary]:
    service = ReviewTaskService(db)
    service.reconcile_overdue_reviews()
    repository = ReviewTaskRepository(db)
    review_tasks = repository.list(status=review_status, session_id=session_id)
    assistant_map = _assistant_name_map(
        db, {item.assistant_id for item in review_tasks}
    )
    session_map = _session_title_map(db, {item.session_id for item in review_tasks})
    summaries = [
        to_review_task_summary(
            item,
            assistant_name=assistant_map.get(item.assistant_id, "未知助理"),
            session_title=session_map.get(item.session_id, "未知会话"),
            sla=TaskSlaSnapshot(**build_review_sla_snapshot(item)),
        )
        for item in review_tasks
    ]
    if sla_status:
        summaries = [item for item in summaries if item.sla.status == sla_status]
    return summaries


@router.get("/{review_id}", response_model=ReviewTaskDetail)
async def get_review_task(
    review_id: str,
    db: Session = Depends(get_db),
) -> ReviewTaskDetail:
    service = ReviewTaskService(db)
    service.reconcile_overdue_reviews()
    repository = ReviewTaskRepository(db)
    review_task = repository.get(review_id)
    if not review_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审核任务不存在。",
        )
    assistant_map = _assistant_name_map(db, {review_task.assistant_id})
    session_map = _session_title_map(db, {review_task.session_id})
    return to_review_task_detail(
        review_task,
        assistant_name=assistant_map.get(review_task.assistant_id, "未知助理"),
        session_title=session_map.get(review_task.session_id, "未知会话"),
        sla=TaskSlaSnapshot(**build_review_sla_snapshot(review_task)),
    )


@router.get("/{review_id}/audit-logs", response_model=list[AuditLogEntry])
async def list_review_audit_logs(
    review_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    event_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[AuditLogEntry]:
    ReviewTaskService(db).reconcile_overdue_reviews()
    review_task = ReviewTaskRepository(db).get(review_id)
    if not review_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审核任务不存在。",
        )

    repository = AuditLogRepository(db)
    audit_logs = repository.list(
        review_id=review_id,
        event_type=event_type,
        limit=limit,
    )
    return [to_audit_log_entry(item) for item in audit_logs]


@router.post(
    "/{review_id}/approve",
    response_model=ReviewTaskDetail,
    dependencies=[Depends(require_permissions("review:write"))],
)
async def approve_review_task(
    review_id: str,
    payload: ReviewApproveRequest,
    db: Session = Depends(get_db),
) -> ReviewTaskDetail:
    service = ReviewTaskService(db)
    service.reconcile_overdue_reviews()
    repository = ReviewTaskRepository(db)
    review_task = repository.get(review_id)
    if not review_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审核任务不存在。",
        )
    try:
        review_task = service.approve(
            review_task=review_task,
            reviewer_note=payload.reviewer_note,
        )
    except ReviewTaskStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    assistant_map = _assistant_name_map(db, {review_task.assistant_id})
    session_map = _session_title_map(db, {review_task.session_id})
    return to_review_task_detail(
        review_task,
        assistant_name=assistant_map.get(review_task.assistant_id, "未知助理"),
        session_title=session_map.get(review_task.session_id, "未知会话"),
        sla=TaskSlaSnapshot(**build_review_sla_snapshot(review_task)),
    )


@router.post(
    "/{review_id}/reject",
    response_model=ReviewTaskDetail,
    dependencies=[Depends(require_permissions("review:write"))],
)
async def reject_review_task(
    review_id: str,
    payload: ReviewRejectRequest,
    db: Session = Depends(get_db),
) -> ReviewTaskDetail:
    service = ReviewTaskService(db)
    service.reconcile_overdue_reviews()
    repository = ReviewTaskRepository(db)
    review_task = repository.get(review_id)
    if not review_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审核任务不存在。",
        )
    try:
        review_task = service.reject(
            review_task=review_task,
            reviewer_note=payload.reviewer_note,
            manual_answer=payload.manual_answer,
        )
    except ReviewTaskStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    assistant_map = _assistant_name_map(db, {review_task.assistant_id})
    session_map = _session_title_map(db, {review_task.session_id})
    return to_review_task_detail(
        review_task,
        assistant_name=assistant_map.get(review_task.assistant_id, "未知助理"),
        session_title=session_map.get(review_task.session_id, "未知会话"),
        sla=TaskSlaSnapshot(**build_review_sla_snapshot(review_task)),
    )
