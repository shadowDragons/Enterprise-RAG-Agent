from pydantic import BaseModel, Field


class ChatCitation(BaseModel):
    chunk_id: str
    document_id: str
    knowledge_base_id: str
    chunk_index: int
    file_name: str
    content: str
    score: float
    vector_score: float = 0.0
    lexical_score: float = 0.0
    embedding_backend: str = ""


class ChatQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    knowledge_base_id: str | None = Field(default=None, max_length=36)
    knowledge_base_ids: list[str] = Field(default_factory=list)
    top_k: int = Field(default=4, ge=1, le=10)


class WorkflowTraceStep(BaseModel):
    node: str
    detail: str


class ChatQueryResponse(BaseModel):
    session_id: str
    selected_knowledge_base_id: str
    selected_kb_ids: list[str] = Field(default_factory=list)
    answer: str
    citations: list[ChatCitation]
    retrieval_count: int
    fallback_reason: str | None = None
    review_id: str | None = None
    review_status: str | None = None
    workflow_trace: list[WorkflowTraceStep] = Field(default_factory=list)
