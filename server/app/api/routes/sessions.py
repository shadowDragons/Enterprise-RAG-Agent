from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps.auth import require_permissions
from app.db.session import get_db
from app.models import Assistant, Message
from app.repositories.audit_logs import AuditLogRepository
from app.repositories.assistants import AssistantRepository
from app.repositories.sessions import SessionRepository
from app.schemas.audit_log import AuditLogEntry, to_audit_log_entry
from app.schemas.session import (
    SessionCreate,
    SessionDeleteResult,
    SessionSummary,
    to_session_summary,
)
from app.services.resource_admin import ResourceAdminService, ResourceAdminStateError
from app.services.session_runtime_view import build_session_runtime_map

router = APIRouter(
    prefix="/sessions",
    tags=["sessions"],
    dependencies=[Depends(require_permissions("session:read"))],
)


def _assistant_name_map(
    db: Session,
    assistant_ids: set[str] | None = None,
) -> dict[str, str]:
    stmt = select(Assistant.assistant_id, Assistant.assistant_name)
    if assistant_ids:
        stmt = stmt.where(Assistant.assistant_id.in_(assistant_ids))
    rows = db.execute(stmt).all()
    return {assistant_id: assistant_name for assistant_id, assistant_name in rows}


def _message_count_map(
    db: Session,
    session_ids: set[str] | None = None,
) -> dict[str, int]:
    stmt = select(Message.session_id, func.count(Message.message_id)).group_by(
        Message.session_id
    )
    if session_ids:
        stmt = stmt.where(Message.session_id.in_(session_ids))
    rows = db.execute(stmt).all()
    return {session_id: count for session_id, count in rows}


@router.get("", response_model=list[SessionSummary])
async def list_sessions(
    assistant_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[SessionSummary]:
    repository = SessionRepository(db)
    sessions = repository.list(assistant_id=assistant_id)
    assistant_ids = {item.assistant_id for item in sessions}
    assistant_map = _assistant_name_map(db, assistant_ids)
    count_map = _message_count_map(db, {item.session_id for item in sessions})
    runtime_map = build_session_runtime_map(db, sessions)
    return [
        to_session_summary(
            item,
            assistant_map.get(item.assistant_id, "未知助理"),
            count_map.get(item.session_id, 0),
            runtime_map.get(item.session_id),
        )
        for item in sessions
    ]


@router.post(
    "",
    response_model=SessionSummary,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions("session:write"))],
)
async def create_session(
    payload: SessionCreate,
    db: Session = Depends(get_db),
) -> SessionSummary:
    assistant_repository = AssistantRepository(db)
    assistant = assistant_repository.get(payload.assistant_id)
    if not assistant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="助理不存在。",
        )

    repository = SessionRepository(db)
    session = repository.create(payload)
    return to_session_summary(session, assistant.assistant_name, 0)


@router.get("/{session_id}", response_model=SessionSummary)
async def get_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> SessionSummary:
    repository = SessionRepository(db)
    session = repository.get(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在。",
        )

    assistant_map = _assistant_name_map(db, {session.assistant_id})
    count_map = _message_count_map(db, {session.session_id})
    runtime_map = build_session_runtime_map(db, [session])
    return to_session_summary(
        session,
        assistant_map.get(session.assistant_id, "未知助理"),
        count_map.get(session.session_id, 0),
        runtime_map.get(session.session_id),
    )


@router.get("/{session_id}/audit-logs", response_model=list[AuditLogEntry])
async def list_session_audit_logs(
    session_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    event_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[AuditLogEntry]:
    session = SessionRepository(db).get(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在。",
        )

    repository = AuditLogRepository(db)
    audit_logs = repository.list(
        session_id=session_id,
        event_type=event_type,
        limit=limit,
    )
    return [to_audit_log_entry(item) for item in audit_logs]


@router.delete(
    "/{session_id}",
    response_model=SessionDeleteResult,
    dependencies=[Depends(require_permissions("session:write"))],
)
async def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> SessionDeleteResult:
    service = ResourceAdminService(db)
    try:
        result = service.delete_session(session_id)
    except ResourceAdminStateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return SessionDeleteResult(**result)
