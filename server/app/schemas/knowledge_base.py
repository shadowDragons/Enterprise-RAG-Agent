from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBaseCreate(BaseModel):
    knowledge_base_name: str = Field(min_length=1, max_length=255)
    description: str = ""
    default_retrieval_top_k: int = Field(default=5, ge=1, le=50)


class KnowledgeBaseUpdate(KnowledgeBaseCreate):
    pass


class KnowledgeBaseSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    knowledge_base_id: str
    knowledge_base_name: str
    description: str
    default_retrieval_top_k: int
    document_count: int
    assistant_binding_count: int
    status: str


class KnowledgeBaseDeleteResult(BaseModel):
    knowledge_base_id: str
    deleted_document_count: int
    deleted_chunk_count: int
    deleted_job_count: int
    unbound_assistant_count: int


def to_knowledge_base_summary(
    knowledge_base,
    document_count: int,
    *,
    assistant_binding_count: int = 0,
) -> KnowledgeBaseSummary:
    return KnowledgeBaseSummary(
        knowledge_base_id=knowledge_base.knowledge_base_id,
        knowledge_base_name=knowledge_base.knowledge_base_name,
        description=knowledge_base.description,
        default_retrieval_top_k=knowledge_base.default_retrieval_top_k,
        document_count=document_count,
        assistant_binding_count=assistant_binding_count,
        status="ready" if document_count > 0 else "empty",
    )
