from app.repositories.audit_logs import AuditLogRepository
from app.schemas.chat import WorkflowTraceStep


def _truncate_text(text: str, *, limit: int = 120) -> str:
    normalized = text.strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."


def _serialize_workflow_trace(workflow_trace) -> list[dict]:
    return [
        item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
        for item in list(workflow_trace or [])
    ]


def _latest_trace(workflow_trace) -> dict:
    trace = _serialize_workflow_trace(workflow_trace)
    if not trace:
        return {}
    latest = trace[-1]
    return {
        "node": str(latest.get("node", "")).strip(),
        "detail": str(latest.get("detail", "")).strip(),
    }


class AuditLogService:
    def __init__(self, db) -> None:
        self.repository = AuditLogRepository(db)

    def log_chat_result(
        self,
        *,
        session,
        assistant,
        prepared,
    ) -> None:
        if prepared.fallback_reason == "intent_clarification_required":
            event_type = "clarification_required"
            event_level = "warning"
            summary = (
                "会话进入待澄清状态，等待用户确认是否切换主题或补充具体问题。"
            )
        else:
            event_type = "chat_completed"
            event_level = "info"
            summary = (
                f"普通问答已完成，已返回问题“{_truncate_text(prepared.resolved_question)}”的回复。"
            )

        self.repository.create(
            assistant_id=assistant.assistant_id,
            session_id=session.session_id,
            review_id=None,
            workflow_thread_id=prepared.workflow_thread_id,
            event_type=event_type,
            event_level=event_level,
            summary=summary,
            detail_payload={
                "question": prepared.question,
                "resolved_question": prepared.resolved_question,
                "current_goal": prepared.current_goal,
                "fallback_reason": prepared.fallback_reason,
                "clarification_type": prepared.clarification_type,
                "clarification_stage": prepared.clarification_stage,
                "clarification_expected_input": prepared.clarification_expected_input,
                "clarification_reason": prepared.clarification_reason,
                "review_reason": prepared.review_reason,
                "selected_knowledge_base_id": prepared.selected_knowledge_base_id,
                "selected_kb_ids": list(prepared.selected_kb_ids),
                "retrieval_count": prepared.retrieval_count,
                "latest_trace": _latest_trace(prepared.workflow_trace),
                "workflow_trace": _serialize_workflow_trace(prepared.workflow_trace),
            },
        )

    def log_review_pending(
        self,
        *,
        session,
        assistant,
        prepared,
        review_task,
    ) -> None:
        self.repository.create(
            assistant_id=assistant.assistant_id,
            session_id=session.session_id,
            review_id=review_task.review_id,
            workflow_thread_id=prepared.workflow_thread_id,
            event_type="review_pending",
            event_level="warning",
            summary="命中审核规则，已创建待审核任务并挂起自动回复。",
            detail_payload={
                "question": prepared.question,
                "resolved_question": prepared.resolved_question,
                "review_reason": prepared.review_reason,
                "pending_message_id": review_task.pending_message_id,
                "selected_knowledge_base_id": prepared.selected_knowledge_base_id,
                "selected_kb_ids": list(prepared.selected_kb_ids),
                "retrieval_count": prepared.retrieval_count,
                "latest_trace": _latest_trace(prepared.workflow_trace),
                "workflow_trace": _serialize_workflow_trace(prepared.workflow_trace),
            },
        )

    def log_review_decision(
        self,
        *,
        review_task,
        workflow_trace: list[WorkflowTraceStep],
        final_answer: str,
    ) -> None:
        event_type = (
            "review_approved" if review_task.status == "approved" else "review_rejected"
        )
        summary = (
            "审核已通过，工作流已恢复并生成最终答案。"
            if review_task.status == "approved"
            else "审核已驳回，已写入人工答案并结束本轮处理。"
        )
        self.repository.create(
            assistant_id=review_task.assistant_id,
            session_id=review_task.session_id,
            review_id=review_task.review_id,
            workflow_thread_id=str(
                (review_task.checkpoint_payload or {}).get("workflow_thread_id", "")
            ).strip(),
            event_type=event_type,
            event_level="info",
            summary=summary,
            detail_payload={
                "question": review_task.question,
                "review_reason": review_task.review_reason,
                "review_status": review_task.status,
                "reviewer_note": review_task.reviewer_note,
                "selected_knowledge_base_id": review_task.selected_knowledge_base_id,
                "selected_kb_ids": list(review_task.selected_kb_ids or []),
                "retrieval_count": int(review_task.retrieval_count),
                "final_answer_preview": _truncate_text(final_answer, limit=200),
                "latest_trace": _latest_trace(workflow_trace),
                "workflow_trace": _serialize_workflow_trace(workflow_trace),
            },
        )

    def log_review_escalation(
        self,
        *,
        review_task,
        escalation_reason: str,
    ) -> None:
        self.repository.create(
            assistant_id=review_task.assistant_id,
            session_id=review_task.session_id,
            review_id=review_task.review_id,
            workflow_thread_id=str(
                (review_task.checkpoint_payload or {}).get("workflow_thread_id", "")
            ).strip(),
            event_type="review_escalated",
            event_level="warning",
            summary="审核任务超时未处理，系统已自动升级等待人工优先处理。",
            detail_payload={
                "question": review_task.question,
                "review_reason": review_task.review_reason,
                "review_status": review_task.status,
                "escalation_level": int(review_task.escalation_level or 0),
                "escalation_reason": escalation_reason.strip(),
                "escalated_at": (
                    review_task.escalated_at.isoformat()
                    if review_task.escalated_at is not None
                    else None
                ),
                "workflow_trace": _serialize_workflow_trace(review_task.workflow_trace),
            },
        )

    def log_review_failure(
        self,
        *,
        review_task,
        action: str,
        error_message: str,
    ) -> None:
        self.repository.create(
            assistant_id=review_task.assistant_id,
            session_id=review_task.session_id,
            review_id=review_task.review_id,
            workflow_thread_id=str(
                (review_task.checkpoint_payload or {}).get("workflow_thread_id", "")
            ).strip(),
            event_type="review_resume_failed",
            event_level="error",
            summary=f"审核{action}失败：{error_message.strip()}",
            detail_payload={
                "action": action,
                "error_message": error_message.strip(),
                "question": review_task.question,
                "review_reason": review_task.review_reason,
                "review_status": review_task.status,
                "workflow_trace": _serialize_workflow_trace(review_task.workflow_trace),
            },
        )
