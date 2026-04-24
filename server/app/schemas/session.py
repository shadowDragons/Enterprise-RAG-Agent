from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SessionCreate(BaseModel):
    assistant_id: str = Field(min_length=1, max_length=36)
    title: str = Field(default="", max_length=255)


class SessionDeleteResult(BaseModel):
    session_id: str
    assistant_id: str
    deleted_message_count: int
    deleted_review_count: int
    deleted_audit_log_count: int
    deleted_checkpoint_count: int


class SessionWorkflowRuntime(BaseModel):
    runtime_schema_version: int | None = None
    runtime_state: str | None = None
    runtime_label: str | None = None
    current_goal: str | None = None
    resolved_question: str | None = None
    pending_question: str | None = None
    clarification_type: str | None = None
    clarification_stage: str | None = None
    clarification_expected_input: str | None = None
    clarification_reason: str | None = None
    pending_review_id: str | None = None
    pending_review_reason: str | None = None
    pending_review_status: str | None = None
    pending_review_escalation_reason: str | None = None
    pending_review_escalated_at: datetime | None = None
    runtime_reason: str | None = None
    waiting_for: str | None = None
    resume_strategy: str | None = None
    latest_node: str | None = None
    latest_node_detail: str | None = None
    workflow_thread_id: str | None = None
    workflow_checkpoint_id: str | None = None
    workflow_checkpoint_updated_at: datetime | None = None
    workflow_source: str | None = None
    workflow_step: int | None = None
    workflow_checkpoint_backend: str | None = None
    workflow_checkpoint_backend_label: str | None = None
    checkpoint_status: str | None = None
    checkpoint_label: str | None = None
    workflow_pending_write_count: int | None = None
    workflow_can_resume: bool | None = None


class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    assistant_id: str
    assistant_name: str
    title: str
    status: str
    message_count: int
    workflow_runtime: SessionWorkflowRuntime | None = None
    created_at: datetime
    updated_at: datetime


def to_session_summary(
    session,
    assistant_name: str,
    message_count: int,
    workflow_runtime: SessionWorkflowRuntime | None = None,
) -> SessionSummary:
    return SessionSummary(
        session_id=session.session_id,
        assistant_id=session.assistant_id,
        assistant_name=assistant_name,
        title=session.title,
        status=session.status,
        message_count=message_count,
        workflow_runtime=workflow_runtime,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )
