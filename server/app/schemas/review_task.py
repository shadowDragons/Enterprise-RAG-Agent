from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.chat import ChatCitation, WorkflowTraceStep
from app.schemas.task_sla import TaskSlaSnapshot


class ReviewTaskSummary(BaseModel):
    review_id: str
    session_id: str
    session_title: str
    assistant_id: str
    assistant_name: str
    status: str
    question: str
    review_reason: str
    selected_knowledge_base_id: str
    selected_kb_ids: list[str] = Field(default_factory=list)
    retrieval_count: int
    escalation_level: int = 0
    escalation_reason: str = ""
    reviewer_note: str = ""
    final_answer: str = ""
    sla: TaskSlaSnapshot
    created_at: datetime
    updated_at: datetime
    escalated_at: datetime | None = None
    reviewed_at: datetime | None = None


class ReviewTaskDetail(ReviewTaskSummary):
    pending_message_id: str
    citations: list[ChatCitation] = Field(default_factory=list)
    workflow_trace: list[WorkflowTraceStep] = Field(default_factory=list)


class ReviewApproveRequest(BaseModel):
    reviewer_note: str = Field(default="", max_length=2000)


class ReviewRejectRequest(BaseModel):
    reviewer_note: str = Field(default="", max_length=2000)
    manual_answer: str = Field(default="", max_length=8000)


def to_review_task_summary(
    review_task,
    *,
    assistant_name: str,
    session_title: str,
    sla: TaskSlaSnapshot,
) -> ReviewTaskSummary:
    return ReviewTaskSummary(
        review_id=review_task.review_id,
        session_id=review_task.session_id,
        session_title=session_title,
        assistant_id=review_task.assistant_id,
        assistant_name=assistant_name,
        status=review_task.status,
        question=review_task.question,
        review_reason=review_task.review_reason,
        selected_knowledge_base_id=review_task.selected_knowledge_base_id,
        selected_kb_ids=review_task.selected_kb_ids,
        retrieval_count=review_task.retrieval_count,
        escalation_level=int(review_task.escalation_level or 0),
        escalation_reason=review_task.escalation_reason,
        reviewer_note=review_task.reviewer_note,
        final_answer=review_task.final_answer,
        sla=sla,
        created_at=review_task.created_at,
        updated_at=review_task.updated_at,
        escalated_at=review_task.escalated_at,
        reviewed_at=review_task.reviewed_at,
    )


def to_review_task_detail(
    review_task,
    *,
    assistant_name: str,
    session_title: str,
    sla: TaskSlaSnapshot,
) -> ReviewTaskDetail:
    return ReviewTaskDetail(
        **to_review_task_summary(
            review_task,
            assistant_name=assistant_name,
            session_title=session_title,
            sla=sla,
        ).model_dump(),
        pending_message_id=review_task.pending_message_id,
        citations=[ChatCitation(**item) for item in review_task.citations],
        workflow_trace=[
            WorkflowTraceStep(**item) for item in review_task.workflow_trace
        ],
    )
