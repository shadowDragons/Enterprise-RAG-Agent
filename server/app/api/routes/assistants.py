from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps.auth import require_permissions
from app.db.session import get_db
from app.models import Session as ChatSession
from app.repositories.assistants import AssistantRepository
from app.schemas.assistant import (
    AssistantCreate,
    AssistantDeleteResult,
    AssistantRestoreVersionRequest,
    AssistantSummary,
    AssistantUpdate,
    AssistantVersionDetail,
    AssistantVersionSummary,
    to_assistant_summary,
    to_assistant_version_detail,
    to_assistant_version_summary,
)
from app.services.assistant_configs import AssistantConfigService, AssistantConfigStateError
from app.services.resource_admin import ResourceAdminService, ResourceAdminStateError

router = APIRouter(
    prefix="/assistants",
    tags=["assistants"],
    dependencies=[Depends(require_permissions("assistant:read"))],
)


def _session_count_map(
    db: Session,
    assistant_ids: set[str] | None = None,
) -> dict[str, int]:
    stmt = select(ChatSession.assistant_id, func.count(ChatSession.session_id)).group_by(
        ChatSession.assistant_id
    )
    if assistant_ids:
        stmt = stmt.where(ChatSession.assistant_id.in_(assistant_ids))
    return {
        assistant_id: count
        for assistant_id, count in db.execute(stmt).all()
    }


@router.get("", response_model=list[AssistantSummary])
async def list_assistants(db: Session = Depends(get_db)) -> list[AssistantSummary]:
    repository = AssistantRepository(db)
    assistants = repository.list()
    count_map = _session_count_map(db, {item.assistant_id for item in assistants})
    return [
        to_assistant_summary(item, session_count=count_map.get(item.assistant_id, 0))
        for item in assistants
    ]


@router.post(
    "",
    response_model=AssistantSummary,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions("assistant:write"))],
)
async def create_assistant(
    payload: AssistantCreate,
    db: Session = Depends(get_db),
) -> AssistantSummary:
    service = AssistantConfigService(db)
    try:
        assistant = service.create(payload)
    except AssistantConfigStateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return to_assistant_summary(assistant, session_count=0)


@router.get("/{assistant_id}", response_model=AssistantSummary)
async def get_assistant(
    assistant_id: str,
    db: Session = Depends(get_db),
) -> AssistantSummary:
    repository = AssistantRepository(db)
    assistant = repository.get(assistant_id)
    if not assistant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="助理不存在。",
        )
    count_map = _session_count_map(db, {assistant.assistant_id})
    return to_assistant_summary(
        assistant,
        session_count=count_map.get(assistant.assistant_id, 0),
    )


@router.put(
    "/{assistant_id}",
    response_model=AssistantSummary,
    dependencies=[Depends(require_permissions("assistant:write"))],
)
async def update_assistant(
    assistant_id: str,
    payload: AssistantUpdate,
    db: Session = Depends(get_db),
) -> AssistantSummary:
    service = AssistantConfigService(db)
    try:
        assistant = service.update(assistant_id, payload)
    except AssistantConfigStateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    count_map = _session_count_map(db, {assistant.assistant_id})
    return to_assistant_summary(
        assistant,
        session_count=count_map.get(assistant.assistant_id, 0),
    )


@router.get(
    "/{assistant_id}/versions",
    response_model=list[AssistantVersionSummary],
)
async def list_assistant_versions(
    assistant_id: str,
    db: Session = Depends(get_db),
) -> list[AssistantVersionSummary]:
    service = AssistantConfigService(db)
    try:
        assistant_versions = service.list_versions(assistant_id)
    except AssistantConfigStateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return [to_assistant_version_summary(item) for item in assistant_versions]


@router.get(
    "/{assistant_id}/versions/{version}",
    response_model=AssistantVersionDetail,
)
async def get_assistant_version(
    assistant_id: str,
    version: int,
    db: Session = Depends(get_db),
) -> AssistantVersionDetail:
    service = AssistantConfigService(db)
    try:
        assistant_version = service.get_version(assistant_id, version)
    except AssistantConfigStateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return to_assistant_version_detail(assistant_version)


@router.post(
    "/{assistant_id}/versions/{version}/restore",
    response_model=AssistantSummary,
    dependencies=[Depends(require_permissions("assistant:write"))],
)
async def restore_assistant_version(
    assistant_id: str,
    version: int,
    payload: AssistantRestoreVersionRequest,
    db: Session = Depends(get_db),
) -> AssistantSummary:
    service = AssistantConfigService(db)
    try:
        assistant = service.restore_version(
            assistant_id,
            version,
            change_note=payload.change_note,
        )
    except AssistantConfigStateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    count_map = _session_count_map(db, {assistant.assistant_id})
    return to_assistant_summary(
        assistant,
        session_count=count_map.get(assistant.assistant_id, 0),
    )


@router.delete(
    "/{assistant_id}",
    response_model=AssistantDeleteResult,
    dependencies=[Depends(require_permissions("assistant:write"))],
)
async def delete_assistant(
    assistant_id: str,
    db: Session = Depends(get_db),
) -> AssistantDeleteResult:
    service = ResourceAdminService(db)
    try:
        result = service.delete_assistant(assistant_id)
    except ResourceAdminStateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return AssistantDeleteResult(**result)
