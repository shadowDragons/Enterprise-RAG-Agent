from dataclasses import dataclass

from app.schemas.chat import WorkflowTraceStep


@dataclass(frozen=True)
class SessionLifecycleState:
    status: str
    runtime_state: str
    runtime_label: str
    waiting_for: str | None
    resume_strategy: str


def resolve_session_lifecycle(
    *,
    fallback_reason: str | None = None,
    clarification_stage: str = "",
    review_decision: str = "",
    review_status: str = "",
) -> SessionLifecycleState:
    normalized_fallback = str(fallback_reason or "").strip()
    normalized_clarification_stage = clarification_stage.strip()
    normalized_review_decision = review_decision.strip()
    normalized_review_status = review_status.strip()

    if normalized_fallback == "review_required":
        if normalized_review_status == "escalated":
            return SessionLifecycleState(
                status="awaiting_review",
                runtime_state="waiting_review_escalated",
                runtime_label="人工审核已超时，等待升级处理",
                waiting_for="escalated_human_review",
                resume_strategy="command_resume",
            )
        return SessionLifecycleState(
            status="awaiting_review",
            runtime_state="waiting_review",
            runtime_label="等待人工审核",
            waiting_for="human_review",
            resume_strategy="command_resume",
        )

    if normalized_fallback == "intent_clarification_required":
        if normalized_clarification_stage == "collect_new_topic_question":
            return SessionLifecycleState(
                status="awaiting_clarification",
                runtime_state="waiting_new_topic_question",
                runtime_label="等待输入新主题问题",
                waiting_for="new_topic_question",
                resume_strategy="new_user_message",
            )
        if normalized_clarification_stage == "collect_current_topic_question":
            return SessionLifecycleState(
                status="awaiting_clarification",
                runtime_state="waiting_clarification_question",
                runtime_label="等待补充具体问题",
                waiting_for="follow_up_question",
                resume_strategy="new_user_message",
            )
        return SessionLifecycleState(
            status="awaiting_clarification",
            runtime_state="waiting_clarification_switch",
            runtime_label="等待确认是否切换主题",
            waiting_for="topic_switch_confirmation",
            resume_strategy="new_user_message",
        )

    if normalized_review_decision == "approved":
        return SessionLifecycleState(
            status="active",
            runtime_state="completed_after_review",
            runtime_label="审核通过并已完成",
            waiting_for=None,
            resume_strategy="none",
        )

    if normalized_review_decision == "rejected":
        return SessionLifecycleState(
            status="active",
            runtime_state="completed_with_manual_review",
            runtime_label="人工驳回并已转人工结论",
            waiting_for=None,
            resume_strategy="none",
        )

    return SessionLifecycleState(
        status="active",
        runtime_state="completed",
        runtime_label="本轮已完成",
        waiting_for=None,
        resume_strategy="none",
    )


def resolve_clarification_stage_from_runtime_state(runtime_state: str) -> str:
    normalized_runtime_state = str(runtime_state or "").strip()
    if normalized_runtime_state == "waiting_new_topic_question":
        return "collect_new_topic_question"
    if normalized_runtime_state == "waiting_clarification_question":
        return "collect_current_topic_question"
    if normalized_runtime_state == "waiting_clarification_switch":
        return "confirm_switch"
    return ""


def build_workflow_runtime_payload(
    *,
    current_goal: str = "",
    resolved_question: str = "",
    pending_question: str = "",
    selected_kb_ids: list[str] | None = None,
    selected_knowledge_base_id: str = "",
    retrieval_count: int | None = None,
    fallback_reason: str | None = None,
    clarification_type: str = "",
    clarification_stage: str = "",
    clarification_expected_input: str = "",
    clarification_reason: str = "",
    review_reason: str = "",
    review_decision: str = "",
    review_status: str = "",
    review_escalation_level: int | None = None,
    review_escalation_reason: str = "",
    review_escalated_at: str = "",
    workflow_trace: list[WorkflowTraceStep] | None = None,
) -> dict:
    trace = list(workflow_trace or [])
    latest_trace = trace[-1] if trace else None
    payload = {
        "runtime_schema_version": 3,
        "latest_trace_node": latest_trace.node if latest_trace else "",
        "latest_trace_detail": latest_trace.detail if latest_trace else "",
    }
    return {
        key: value
        for key, value in payload.items()
        if _should_keep_runtime_value(value)
    }


def _should_keep_runtime_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, dict):
        return bool(value)
    return True
