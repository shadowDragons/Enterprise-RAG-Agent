from dataclasses import dataclass, replace

from app.core.config import get_settings
from app.integrations.langgraph_checkpointer import get_workflow_checkpointer
from app.repositories.messages import MessageRepository
from app.repositories.sessions import SessionRepository
from app.schemas.chat import ChatCitation, ChatQueryResponse, WorkflowTraceStep
from app.services.audit_logs import AuditLogService
from app.services.review_tasks import ReviewTaskService
from app.services.workflow_runtime import (
    build_workflow_runtime_payload,
    resolve_session_lifecycle,
)
from app.workflows.chat_graph import build_chat_workflow


@dataclass
class PreparedWorkflowData:
    session_id: str
    workflow_thread_id: str
    question: str
    resolved_question: str
    selected_knowledge_base_id: str
    selected_kb_ids: list[str]
    effective_question: str
    current_goal: str
    memory_summary: str
    intent_drift_score: float
    clarification_type: str
    clarification_stage: str
    clarification_expected_input: str
    clarification_reason: str
    review_reason: str
    citations: list[ChatCitation]
    retrieval_count: int
    fallback_reason: str | None
    workflow_trace: list[WorkflowTraceStep]
    review_id: str | None = None
    review_status: str | None = None


@dataclass
class PreparedChatResult(PreparedWorkflowData):
    answer: str = ""


class SessionChatService:
    def __init__(self, db):
        self.db = db
        self.message_repository = MessageRepository(db)
        self.session_repository = SessionRepository(db)
        self.audit_log_service = AuditLogService(db)
        self.review_task_service = ReviewTaskService(db)
        checkpointer = get_workflow_checkpointer()
        self.preparation_workflow = build_chat_workflow(
            include_compose_answer=False,
            checkpointer=checkpointer,
        )

    def prepare_stream_context(
        self,
        session,
        assistant,
        question: str,
        requested_knowledge_base_ids: list[str],
        top_k: int,
    ) -> PreparedWorkflowData:
        prepared, _ = self._invoke_workflow(
            session=session,
            assistant=assistant,
            question=question,
            requested_knowledge_base_ids=requested_knowledge_base_ids,
            top_k=top_k,
            workflow=self.preparation_workflow,
        )
        return prepared

    def build_result(
        self,
        *,
        context: PreparedWorkflowData,
        answer: str,
        fallback_reason: str | None = None,
        workflow_trace: list[WorkflowTraceStep] | None = None,
    ) -> PreparedChatResult:
        return PreparedChatResult(
            session_id=context.session_id,
            workflow_thread_id=context.workflow_thread_id,
            question=context.question,
            resolved_question=context.resolved_question,
            selected_knowledge_base_id=context.selected_knowledge_base_id,
            selected_kb_ids=context.selected_kb_ids,
            effective_question=context.effective_question,
            current_goal=context.current_goal,
            memory_summary=context.memory_summary,
            intent_drift_score=context.intent_drift_score,
            clarification_type=context.clarification_type,
            clarification_stage=context.clarification_stage,
            clarification_expected_input=context.clarification_expected_input,
            clarification_reason=context.clarification_reason,
            review_reason=context.review_reason,
            citations=context.citations,
            retrieval_count=context.retrieval_count,
            fallback_reason=fallback_reason,
            workflow_trace=workflow_trace or context.workflow_trace,
            review_id=context.review_id,
            review_status=context.review_status,
            answer=answer,
        )

    def persist_assistant_message(self, prepared: PreparedChatResult):
        return self.message_repository.create(
            session_id=prepared.session_id,
            role="assistant",
            content=prepared.answer,
            citations=[item.model_dump() for item in prepared.citations],
        )

    def finalize_review_hold(
        self,
        *,
        session,
        assistant,
        prepared: PreparedChatResult,
    ) -> PreparedChatResult:
        pending_message = self.persist_assistant_message(prepared)
        self._update_session_status(
            session_id=session.session_id,
            workflow_thread_id=prepared.workflow_thread_id,
            fallback_reason=prepared.fallback_reason,
            clarification_stage=prepared.clarification_stage,
            runtime_reason=self._build_runtime_reason(prepared),
            runtime_current_goal=prepared.current_goal,
            runtime_resolved_question=prepared.resolved_question,
            runtime_pending_question=(
                prepared.resolved_question
                if prepared.fallback_reason == "intent_clarification_required"
                and prepared.clarification_stage == "confirm_switch"
                else ""
            ),
            runtime_clarification_type=prepared.clarification_type,
            runtime_clarification_stage=prepared.clarification_stage,
            runtime_clarification_expected_input=prepared.clarification_expected_input,
            runtime_clarification_reason=prepared.clarification_reason,
            runtime_context=self._build_runtime_context(prepared),
        )
        review_task = self.review_task_service.create_pending_review(
            assistant=assistant,
            prepared=prepared,
            pending_message_id=pending_message.message_id,
        )
        self.audit_log_service.log_review_pending(
            session=session,
            assistant=assistant,
            prepared=prepared,
            review_task=review_task,
        )
        return replace(
            prepared,
            review_id=review_task.review_id,
            review_status=review_task.status,
        )

    def finalize_turn(
        self,
        *,
        session,
        assistant,
        prepared: PreparedChatResult,
    ) -> PreparedChatResult:
        if prepared.fallback_reason == "review_required":
            return self.finalize_review_hold(
                session=session,
                assistant=assistant,
                prepared=prepared,
            )

        self.persist_assistant_message(prepared)
        self._update_session_status(
            session_id=session.session_id,
            workflow_thread_id=prepared.workflow_thread_id,
            fallback_reason=prepared.fallback_reason,
            clarification_stage=prepared.clarification_stage,
            runtime_reason=self._build_runtime_reason(prepared),
            runtime_current_goal=prepared.current_goal,
            runtime_resolved_question=prepared.resolved_question,
            runtime_pending_question=(
                prepared.resolved_question
                if prepared.fallback_reason == "intent_clarification_required"
                and prepared.clarification_stage == "confirm_switch"
                else ""
            ),
            runtime_clarification_type=prepared.clarification_type,
            runtime_clarification_stage=prepared.clarification_stage,
            runtime_clarification_expected_input=prepared.clarification_expected_input,
            runtime_clarification_reason=prepared.clarification_reason,
            runtime_context=self._build_runtime_context(prepared),
        )
        self.audit_log_service.log_chat_result(
            session=session,
            assistant=assistant,
            prepared=prepared,
        )
        return prepared

    def to_response(self, prepared: PreparedChatResult) -> ChatQueryResponse:
        return ChatQueryResponse(
            session_id=prepared.session_id,
            selected_knowledge_base_id=prepared.selected_knowledge_base_id,
            selected_kb_ids=prepared.selected_kb_ids,
            answer=prepared.answer,
            citations=prepared.citations,
            retrieval_count=prepared.retrieval_count,
            fallback_reason=prepared.fallback_reason,
            review_id=prepared.review_id,
            review_status=prepared.review_status,
            workflow_trace=prepared.workflow_trace,
        )

    def _start_turn(self, *, session, question: str) -> tuple[str, str]:
        normalized_question = question.strip()
        user_message = self.message_repository.create(
            session_id=session.session_id,
            role="user",
            content=normalized_question,
            citations=[],
        )

        if session.title == "新会话":
            session.title = normalized_question[:20] or "新会话"
            self.db.commit()

        return normalized_question, user_message.message_id

    def _build_workflow_input(
        self,
        *,
        assistant,
        question: str,
        requested_knowledge_base_ids: list[str],
        message_history: list[dict],
        session_status: str,
        session_runtime_context: dict,
        session_runtime_state: str,
        top_k: int,
    ) -> dict:
        return {
            "assistant_id": assistant.assistant_id,
            "assistant_name": assistant.assistant_name,
            "assistant_config": {
                "assistant_id": assistant.assistant_id,
                "assistant_name": assistant.assistant_name,
                "system_prompt": assistant.system_prompt,
                "default_model": assistant.default_model,
                "default_kb_ids": assistant.default_kb_ids,
                "review_rules": assistant.review_rules,
                "review_enabled": assistant.review_enabled,
            },
            "session_status": session_status,
            "session_runtime_context": dict(session_runtime_context),
            "session_runtime_state": session_runtime_state,
            "question": question,
            "requested_knowledge_base_ids": requested_knowledge_base_ids,
            "message_history": message_history,
            "top_k": top_k,
            "review_interrupt_enabled": True,
        }

    def _invoke_workflow(
        self,
        *,
        session,
        assistant,
        question: str,
        requested_knowledge_base_ids: list[str],
        top_k: int,
        workflow,
    ) -> tuple[PreparedWorkflowData, dict]:
        message_history = self._load_recent_messages(session.session_id)
        normalized_question, workflow_thread_id = self._start_turn(
            session=session,
            question=question,
        )
        workflow_result = workflow.invoke(
            self._build_workflow_input(
                assistant=assistant,
                question=normalized_question,
                requested_knowledge_base_ids=requested_knowledge_base_ids,
                message_history=message_history,
                session_status=session.status,
                session_runtime_context=self._build_session_runtime_context(session),
                session_runtime_state=session.runtime_state,
                top_k=top_k,
            ),
            config=self._build_workflow_config(workflow_thread_id),
        )
        prepared = self._build_prepared_workflow_data(
            session_id=session.session_id,
            workflow_thread_id=workflow_thread_id,
            question=normalized_question,
            workflow_result=workflow_result,
        )
        return prepared, workflow_result

    def _build_prepared_workflow_data(
        self,
        *,
        session_id: str,
        workflow_thread_id: str,
        question: str,
        workflow_result: dict,
    ) -> PreparedWorkflowData:
        citations = workflow_result.get("citations", [])
        retrieval_count = int(workflow_result.get("retrieval_count", len(citations)))
        fallback_reason = workflow_result.get("fallback_reason")
        if self._has_interrupt(workflow_result):
            fallback_reason = "review_required"
        return PreparedWorkflowData(
            session_id=session_id,
            workflow_thread_id=workflow_thread_id,
            question=question,
            resolved_question=workflow_result.get("resolved_question", question),
            selected_knowledge_base_id=workflow_result.get(
                "selected_knowledge_base_id", ""
            ),
            selected_kb_ids=workflow_result.get("selected_kb_ids", []),
            effective_question=workflow_result.get("effective_question", question),
            current_goal=workflow_result.get("current_goal", question),
            memory_summary=workflow_result.get("memory_summary", ""),
            intent_drift_score=float(workflow_result.get("intent_drift_score", 0.0)),
            clarification_type=str(
                workflow_result.get("clarification_type", "")
            ).strip(),
            clarification_stage=str(
                workflow_result.get("clarification_stage", "")
            ).strip(),
            clarification_expected_input=str(
                workflow_result.get("clarification_expected_input", "")
            ).strip(),
            clarification_reason=str(
                workflow_result.get("clarification_reason", "")
            ).strip(),
            review_reason=workflow_result.get("review_reason", ""),
            citations=citations,
            retrieval_count=retrieval_count,
            fallback_reason=fallback_reason,
            workflow_trace=workflow_result.get("workflow_trace", []),
        )

    def _build_workflow_config(self, workflow_thread_id: str) -> dict:
        return {
            "configurable": {
                "thread_id": workflow_thread_id,
            }
        }

    def _has_interrupt(self, workflow_result: dict) -> bool:
        return bool(workflow_result.get("__interrupt__"))

    def _load_recent_messages(self, session_id: str) -> list[dict]:
        settings = get_settings()
        messages = self.message_repository.list_recent(
            session_id=session_id,
            limit=settings.chat_memory_message_window,
        )
        return [
            {
                "role": item.role,
                "content": item.content,
            }
            for item in messages
            if item.content.strip()
        ]

    def _update_session_status(
        self,
        *,
        session_id: str,
        workflow_thread_id: str,
        fallback_reason: str | None,
        clarification_stage: str = "",
        review_decision: str = "",
        runtime_reason: str = "",
        runtime_current_goal: str = "",
        runtime_resolved_question: str = "",
        runtime_pending_question: str = "",
        runtime_clarification_type: str = "",
        runtime_clarification_stage: str = "",
        runtime_clarification_expected_input: str = "",
        runtime_clarification_reason: str = "",
        runtime_context: dict | None = None,
    ) -> None:
        lifecycle = resolve_session_lifecycle(
            fallback_reason=fallback_reason,
            clarification_stage=clarification_stage,
            review_decision=review_decision,
        )
        self.session_repository.update_runtime(
            session_id,
            status=lifecycle.status,
            runtime_state=lifecycle.runtime_state,
            runtime_label=lifecycle.runtime_label,
            runtime_waiting_for=lifecycle.waiting_for or "",
            runtime_resume_strategy=lifecycle.resume_strategy,
            workflow_thread_id=workflow_thread_id,
            runtime_reason=runtime_reason,
            runtime_current_goal=runtime_current_goal,
            runtime_resolved_question=runtime_resolved_question,
            runtime_pending_question=runtime_pending_question,
            runtime_clarification_type=runtime_clarification_type,
            runtime_clarification_stage=runtime_clarification_stage,
            runtime_clarification_expected_input=runtime_clarification_expected_input,
            runtime_clarification_reason=runtime_clarification_reason,
            runtime_context=runtime_context,
        )

    def _build_runtime_reason(self, prepared: PreparedChatResult) -> str:
        if prepared.fallback_reason == "review_required":
            return prepared.review_reason.strip()
        if prepared.fallback_reason == "intent_clarification_required":
            if prepared.clarification_stage == "collect_new_topic_question":
                return (
                    "用户已明确表示要切换主题，"
                    "但当前消息未包含新主题的具体问题，等待用户补充。"
                )
            if prepared.clarification_stage == "collect_current_topic_question":
                return (
                    f"用户表示继续围绕会话主线“{prepared.current_goal}”提问，"
                    "但当前回复未形成具体问题，等待用户补充明确追问。"
                )
            similarity = max(0.0, 1.0 - prepared.intent_drift_score)
            return (
                f"当前问题与会话主线“{prepared.current_goal}”关联较弱，"
                f"相似度 {similarity:.2f}，等待用户确认是否切换主题。"
            )
        return ""

    def _build_runtime_context(self, prepared: PreparedChatResult) -> dict:
        pending_question = ""
        if (
            prepared.fallback_reason == "intent_clarification_required"
            and prepared.clarification_stage == "confirm_switch"
        ):
            pending_question = prepared.resolved_question

        return build_workflow_runtime_payload(
            current_goal=prepared.current_goal,
            resolved_question=prepared.resolved_question,
            pending_question=pending_question,
            selected_kb_ids=prepared.selected_kb_ids,
            selected_knowledge_base_id=prepared.selected_knowledge_base_id,
            retrieval_count=prepared.retrieval_count,
            fallback_reason=prepared.fallback_reason,
            clarification_type=prepared.clarification_type,
            clarification_stage=prepared.clarification_stage,
            clarification_expected_input=prepared.clarification_expected_input,
            clarification_reason=prepared.clarification_reason,
            review_reason=prepared.review_reason,
            review_status="pending" if prepared.fallback_reason == "review_required" else "",
            workflow_trace=prepared.workflow_trace,
        )

    def _build_session_runtime_context(self, session) -> dict:
        payload = {
            "current_goal": getattr(session, "runtime_current_goal", ""),
            "resolved_question": getattr(session, "runtime_resolved_question", ""),
            "pending_question": getattr(session, "runtime_pending_question", ""),
            "clarification_type": getattr(session, "runtime_clarification_type", ""),
            "clarification_stage": getattr(session, "runtime_clarification_stage", ""),
            "clarification_expected_input": getattr(
                session, "runtime_clarification_expected_input", ""
            ),
            "clarification_reason": getattr(session, "runtime_clarification_reason", ""),
        }
        return {
            key: value.strip()
            for key, value in payload.items()
            if isinstance(value, str) and value.strip()
        }
