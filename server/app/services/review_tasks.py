from datetime import datetime, timezone

from langgraph.types import Command

from app.core.task_sla import HUMAN_REVIEW_SLA, build_review_sla_snapshot
from app.integrations.langgraph_checkpointer import get_workflow_checkpointer
from app.repositories.messages import MessageRepository
from app.repositories.review_tasks import ReviewTaskRepository
from app.repositories.sessions import SessionRepository
from app.schemas.chat import WorkflowTraceStep
from app.services.audit_logs import AuditLogService
from app.services.workflow_runtime import (
    build_workflow_runtime_payload,
    resolve_session_lifecycle,
)
from app.workflows.chat_graph import build_chat_workflow


class ReviewTaskStateError(RuntimeError):
    """审核任务状态不允许当前操作时抛出。"""


class ReviewTaskService:
    """管理 review task 的创建、恢复和人工结论落库。"""

    def __init__(self, db) -> None:
        self.db = db
        self.review_task_repository = ReviewTaskRepository(db)
        self.message_repository = MessageRepository(db)
        self.session_repository = SessionRepository(db)
        self.audit_log_service = AuditLogService(db)

    def create_pending_review(
        self,
        *,
        assistant,
        prepared,
        pending_message_id: str,
    ):
        return self.review_task_repository.create(
            session_id=prepared.session_id,
            assistant_id=assistant.assistant_id,
            pending_message_id=pending_message_id,
            question=prepared.resolved_question,
            review_reason=prepared.review_reason,
            selected_knowledge_base_id=prepared.selected_knowledge_base_id,
            selected_kb_ids=prepared.selected_kb_ids,
            citations=[item.model_dump() for item in prepared.citations],
            retrieval_count=prepared.retrieval_count,
            checkpoint_payload={
                "workflow_thread_id": prepared.workflow_thread_id,
            },
            workflow_trace=[
                item.model_dump(mode="json") for item in prepared.workflow_trace
            ],
        )

    def reconcile_overdue_reviews(self) -> int:
        escalated_count = 0
        for review_task in self.review_task_repository.list_pending():
            if build_review_sla_snapshot(review_task).get("status") != "breached":
                continue
            self._escalate_review_task(review_task)
            escalated_count += 1
        return escalated_count

    def approve(
        self,
        *,
        review_task,
        reviewer_note: str = "",
    ):
        try:
            self._ensure_pending(review_task)
            note = reviewer_note.strip()
            answer, citations, workflow_trace = self._resume_workflow(
                review_task=review_task,
                action="approve",
                reviewer_note=note,
            )

            self._update_pending_message(
                review_task.pending_message_id,
                content=answer,
                citations=citations,
            )
            self._set_session_active(
                review_task=review_task,
                workflow_trace=workflow_trace,
                review_decision="approved",
            )
            review_task = self.review_task_repository.mark_reviewed(
                review_task,
                status="approved",
                reviewer_note=note,
                final_answer=answer,
                workflow_trace=[
                    item.model_dump(mode="json") for item in workflow_trace
                ],
            )
            self.audit_log_service.log_review_decision(
                review_task=review_task,
                workflow_trace=workflow_trace,
                final_answer=answer,
            )
            return review_task
        except ReviewTaskStateError as exc:
            self.audit_log_service.log_review_failure(
                review_task=review_task,
                action="通过",
                error_message=str(exc),
            )
            raise

    def reject(
        self,
        *,
        review_task,
        reviewer_note: str = "",
        manual_answer: str = "",
    ):
        try:
            self._ensure_pending(review_task)
            note = reviewer_note.strip()
            manual = manual_answer.strip()
            answer, citations, workflow_trace = self._resume_workflow(
                review_task=review_task,
                action="reject",
                reviewer_note=note,
                manual_answer=manual,
            )

            self._update_pending_message(
                review_task.pending_message_id,
                content=answer,
                citations=citations,
            )
            self._set_session_active(
                review_task=review_task,
                workflow_trace=workflow_trace,
                review_decision="rejected",
            )
            review_task = self.review_task_repository.mark_reviewed(
                review_task,
                status="rejected",
                reviewer_note=note,
                final_answer=answer,
                workflow_trace=[
                    item.model_dump(mode="json") for item in workflow_trace
                ],
            )
            self.audit_log_service.log_review_decision(
                review_task=review_task,
                workflow_trace=workflow_trace,
                final_answer=answer,
            )
            return review_task
        except ReviewTaskStateError as exc:
            self.audit_log_service.log_review_failure(
                review_task=review_task,
                action="驳回",
                error_message=str(exc),
            )
            raise

    def _resume_workflow(
        self,
        *,
        review_task,
        action: str,
        reviewer_note: str,
        manual_answer: str = "",
    ) -> tuple[str, list[dict], list[WorkflowTraceStep]]:
        workflow_thread_id = self._load_workflow_thread_id(review_task)

        workflow = build_chat_workflow(
            include_compose_answer=True,
            checkpointer=get_workflow_checkpointer(),
        )
        workflow_result = workflow.invoke(
            Command(
                resume={
                    "action": action,
                    "reviewer_note": reviewer_note,
                    "manual_answer": manual_answer,
                }
            ),
            config={
                "configurable": {
                    "thread_id": workflow_thread_id,
                }
            },
        )
        answer = str(workflow_result.get("answer", "")).strip()
        if not answer:
            raise ReviewTaskStateError("审核恢复未生成最终答案。")

        citations = [
            item.model_dump() if hasattr(item, "model_dump") else item
            for item in workflow_result.get("citations", [])
        ]
        workflow_trace = self._normalize_workflow_trace(
            workflow_result.get("workflow_trace", review_task.workflow_trace)
        )
        return answer, citations, workflow_trace

    def _load_workflow_trace(self, review_task) -> list[WorkflowTraceStep]:
        return [WorkflowTraceStep(**item) for item in review_task.workflow_trace]

    def _normalize_workflow_trace(self, workflow_trace) -> list[WorkflowTraceStep]:
        return [
            item if isinstance(item, WorkflowTraceStep) else WorkflowTraceStep(**item)
            for item in workflow_trace
        ]

    def _load_workflow_thread_id(self, review_task) -> str:
        payload = review_task.checkpoint_payload or {}
        workflow_thread_id = str(payload.get("workflow_thread_id", "")).strip()
        if workflow_thread_id:
            return workflow_thread_id
        raise ReviewTaskStateError("审核任务缺少 workflow thread 信息，无法恢复。")

    def _ensure_pending(self, review_task) -> None:
        if review_task.status not in {"pending", "escalated"}:
            raise ReviewTaskStateError("当前审核任务已处理，不能重复提交审核结论。")

    def _update_pending_message(
        self,
        message_id: str,
        *,
        content: str,
        citations: list[dict],
    ) -> None:
        updated = self.message_repository.update(
            message_id,
            content=content,
            citations=citations,
        )
        if not updated:
            raise ReviewTaskStateError("待审核消息不存在，无法回写审核结果。")

    def _format_reviewer_note(self, reviewer_note: str) -> str:
        note = reviewer_note.strip()
        if not note:
            return ""
        return f" 审核意见：{note}"

    def _set_session_active(
        self,
        *,
        review_task,
        workflow_trace: list[WorkflowTraceStep],
        review_decision: str,
    ) -> None:
        lifecycle = resolve_session_lifecycle(review_decision=review_decision)
        self.session_repository.update_runtime(
            review_task.session_id,
            status=lifecycle.status,
            runtime_state=lifecycle.runtime_state,
            runtime_label=lifecycle.runtime_label,
            runtime_waiting_for=lifecycle.waiting_for or "",
            runtime_resume_strategy=lifecycle.resume_strategy,
            workflow_thread_id=self._load_workflow_thread_id(review_task),
            runtime_reason="",
            runtime_current_goal=review_task.question,
            runtime_resolved_question=review_task.question,
            runtime_pending_question="",
            runtime_clarification_type="",
            runtime_clarification_stage="",
            runtime_clarification_expected_input="",
            runtime_clarification_reason="",
            runtime_context=build_workflow_runtime_payload(
                current_goal=review_task.question,
                resolved_question=review_task.question,
                selected_kb_ids=list(review_task.selected_kb_ids or []),
                selected_knowledge_base_id=review_task.selected_knowledge_base_id,
                retrieval_count=int(review_task.retrieval_count),
                review_reason=review_task.review_reason,
                review_decision=review_decision,
                review_status=review_decision,
                review_escalation_level=int(review_task.escalation_level or 0),
                review_escalation_reason=review_task.escalation_reason,
                review_escalated_at=(
                    review_task.escalated_at.isoformat()
                    if review_task.escalated_at is not None
                    else ""
                ),
                workflow_trace=workflow_trace,
            ),
        )

    def _escalate_review_task(self, review_task):
        escalated_at = datetime.now(timezone.utc)
        escalation_reason = (
            f"人工审核超过 {HUMAN_REVIEW_SLA.target_seconds} 秒仍未处理，"
            "系统已自动升级并要求优先人工处理。"
        )
        review_task = self.review_task_repository.mark_escalated(
            review_task,
            escalation_reason=escalation_reason,
            escalation_level=max(1, int(review_task.escalation_level or 0) + 1),
            escalated_at=escalated_at,
        )
        lifecycle = resolve_session_lifecycle(
            fallback_reason="review_required",
            review_status=review_task.status,
        )
        self.session_repository.update_runtime(
            review_task.session_id,
            status=lifecycle.status,
            runtime_state=lifecycle.runtime_state,
            runtime_label=lifecycle.runtime_label,
            runtime_waiting_for=lifecycle.waiting_for or "",
            runtime_resume_strategy=lifecycle.resume_strategy,
            workflow_thread_id=self._load_workflow_thread_id(review_task),
            runtime_reason=escalation_reason,
            runtime_current_goal=review_task.question,
            runtime_resolved_question=review_task.question,
            runtime_pending_question="",
            runtime_clarification_type="",
            runtime_clarification_stage="",
            runtime_clarification_expected_input="",
            runtime_clarification_reason="",
            runtime_context=build_workflow_runtime_payload(
                current_goal=review_task.question,
                resolved_question=review_task.question,
                selected_kb_ids=list(review_task.selected_kb_ids or []),
                selected_knowledge_base_id=review_task.selected_knowledge_base_id,
                retrieval_count=int(review_task.retrieval_count),
                fallback_reason="review_required",
                review_reason=review_task.review_reason,
                review_status=review_task.status,
                review_escalation_level=int(review_task.escalation_level or 0),
                review_escalation_reason=review_task.escalation_reason,
                review_escalated_at=(
                    review_task.escalated_at.isoformat()
                    if review_task.escalated_at is not None
                    else ""
                ),
                workflow_trace=self._load_workflow_trace(review_task),
            ),
        )
        self.audit_log_service.log_review_escalation(
            review_task=review_task,
            escalation_reason=escalation_reason,
        )
        return review_task
