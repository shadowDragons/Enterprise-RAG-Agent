from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps.auth import require_permissions
from app.db.session import get_db
from app.models import Assistant, Document
from app.repositories.knowledge_bases import KnowledgeBaseRepository
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseDeleteResult,
    KnowledgeBaseSummary,
    KnowledgeBaseUpdate,
    to_knowledge_base_summary,
)
from app.services.resource_admin import ResourceAdminService, ResourceAdminStateError

router = APIRouter(
    prefix="/knowledge-bases",
    tags=["knowledge-bases"],
    dependencies=[Depends(require_permissions("knowledge_base:read"))],
)


def _document_count_map(db: Session) -> dict[str, int]:
    stmt = (
        select(Document.knowledge_base_id, func.count(Document.document_id))
        .group_by(Document.knowledge_base_id)
    )
    rows = db.execute(stmt).all()
    return {knowledge_base_id: count for knowledge_base_id, count in rows}


def _assistant_binding_count_map(db: Session) -> dict[str, int]:
    result: dict[str, int] = {}
    for assistant in db.scalars(select(Assistant)).all():
        for knowledge_base_id in list(assistant.default_kb_ids or []):
            result[knowledge_base_id] = result.get(knowledge_base_id, 0) + 1
    return result


@router.get("", response_model=list[KnowledgeBaseSummary])
async def list_knowledge_bases(
    db: Session = Depends(get_db),
) -> list[KnowledgeBaseSummary]:
    repository = KnowledgeBaseRepository(db)
    count_map = _document_count_map(db)
    binding_count_map = _assistant_binding_count_map(db)
    return [
        to_knowledge_base_summary(
            item,
            count_map.get(item.knowledge_base_id, 0),
            assistant_binding_count=binding_count_map.get(item.knowledge_base_id, 0),
        )
        for item in repository.list()
    ]


@router.post(
    "",
    response_model=KnowledgeBaseSummary,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions("knowledge_base:write"))],
)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    db: Session = Depends(get_db),
) -> KnowledgeBaseSummary:
    repository = KnowledgeBaseRepository(db)
    knowledge_base = repository.create(payload)
    binding_count_map = _assistant_binding_count_map(db)
    return to_knowledge_base_summary(
        knowledge_base,
        0,
        assistant_binding_count=binding_count_map.get(knowledge_base.knowledge_base_id, 0),
    )


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseSummary)
async def get_knowledge_base(
    knowledge_base_id: str,
    db: Session = Depends(get_db),
) -> KnowledgeBaseSummary:
    repository = KnowledgeBaseRepository(db)
    knowledge_base = repository.get(knowledge_base_id)
    if not knowledge_base:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在。",
        )
    count_map = _document_count_map(db)
    binding_count_map = _assistant_binding_count_map(db)
    return to_knowledge_base_summary(
        knowledge_base,
        count_map.get(knowledge_base.knowledge_base_id, 0),
        assistant_binding_count=binding_count_map.get(knowledge_base.knowledge_base_id, 0),
    )


@router.put(
    "/{knowledge_base_id}",
    response_model=KnowledgeBaseSummary,
    dependencies=[Depends(require_permissions("knowledge_base:write"))],
)
async def update_knowledge_base(
    knowledge_base_id: str,
    payload: KnowledgeBaseUpdate,
    db: Session = Depends(get_db),
) -> KnowledgeBaseSummary:
    service = ResourceAdminService(db)
    try:
        knowledge_base = service.update_knowledge_base(knowledge_base_id, payload)
    except ResourceAdminStateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    count_map = _document_count_map(db)
    binding_count_map = _assistant_binding_count_map(db)
    return to_knowledge_base_summary(
        knowledge_base,
        count_map.get(knowledge_base.knowledge_base_id, 0),
        assistant_binding_count=binding_count_map.get(knowledge_base.knowledge_base_id, 0),
    )


@router.delete(
    "/{knowledge_base_id}",
    response_model=KnowledgeBaseDeleteResult,
    dependencies=[Depends(require_permissions("knowledge_base:write"))],
)
async def delete_knowledge_base(
    knowledge_base_id: str,
    db: Session = Depends(get_db),
) -> KnowledgeBaseDeleteResult:
    service = ResourceAdminService(db)
    try:
        result = service.delete_knowledge_base(knowledge_base_id)
    except ResourceAdminStateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return KnowledgeBaseDeleteResult(**result)
