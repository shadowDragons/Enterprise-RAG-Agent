from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps.auth import require_permissions
from app.db.session import get_db
from app.repositories.documents import DocumentRepository
from app.repositories.knowledge_bases import KnowledgeBaseRepository
from app.schemas.document import (
    DocumentDeleteResult,
    DocumentSummary,
    DocumentUploadAccepted,
    to_document_summary,
    to_document_upload_accepted,
)
from app.services.document_ingestion import (
    DocumentIngestionService,
    DocumentIngestionStateError,
    process_document_ingestion_job,
)
from app.services.resource_admin import ResourceAdminService, ResourceAdminStateError

router = APIRouter(
    prefix="/knowledge-bases",
    tags=["documents"],
    dependencies=[Depends(require_permissions("document:read"))],
)


@router.get("/{knowledge_base_id}/documents", response_model=list[DocumentSummary])
async def list_documents(
    knowledge_base_id: str,
    db: Session = Depends(get_db),
) -> list[DocumentSummary]:
    knowledge_base_repository = KnowledgeBaseRepository(db)
    knowledge_base = knowledge_base_repository.get(knowledge_base_id)
    if not knowledge_base:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在。",
        )

    repository = DocumentRepository(db)
    return [
        to_document_summary(item)
        for item in repository.list(knowledge_base_id=knowledge_base_id)
    ]


@router.post(
    "/{knowledge_base_id}/documents/upload",
    response_model=DocumentUploadAccepted,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions("document:write"))],
)
async def upload_document(
    knowledge_base_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> DocumentUploadAccepted:
    knowledge_base_repository = KnowledgeBaseRepository(db)
    knowledge_base = knowledge_base_repository.get(knowledge_base_id)
    if not knowledge_base:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在。",
        )
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先选择要上传的文件。",
        )

    service = DocumentIngestionService(db)
    try:
        document, job = service.create_upload_task(knowledge_base_id, file)
    except DocumentIngestionStateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    background_tasks.add_task(
        process_document_ingestion_job,
        document.document_id,
        job.job_id,
    )
    return to_document_upload_accepted(document, job)


@router.delete(
    "/{knowledge_base_id}/documents/{document_id}",
    response_model=DocumentDeleteResult,
    dependencies=[Depends(require_permissions("document:write"))],
)
async def delete_document(
    knowledge_base_id: str,
    document_id: str,
    db: Session = Depends(get_db),
) -> DocumentDeleteResult:
    knowledge_base_repository = KnowledgeBaseRepository(db)
    knowledge_base = knowledge_base_repository.get(knowledge_base_id)
    if not knowledge_base:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在。",
        )

    repository = DocumentRepository(db)
    document = repository.get(document_id)
    if not document or document.knowledge_base_id != knowledge_base_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在。",
        )

    service = ResourceAdminService(db)
    try:
        result = service.delete_document(document_id)
    except ResourceAdminStateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return DocumentDeleteResult(**result)
