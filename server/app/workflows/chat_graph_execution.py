from langgraph.types import interrupt

from app.core.config import get_settings
from app.core.review_rules import evaluate_review_hit
from app.schemas.chat import ChatCitation
from app.services.answer_generation import (
    AnswerGenerationService,
    build_intent_clarification_answer,
    build_no_knowledge_base_answer,
    build_no_retrieval_hits_answer,
    build_review_rejected_answer,
    build_review_required_answer,
)
from app.services.retrieval import RetrievalService
from app.workflows.chat_graph_support import (
    ChatWorkflowState,
    _append_trace,
    _format_kb_scope_label,
)


def _retrieve_citation_dicts(
    *,
    state: ChatWorkflowState,
    retrieval_service: RetrievalService,
    selected_kb_ids: list[str],
    selected_knowledge_base_id: str,
) -> list[dict]:
    if len(selected_kb_ids) <= 1:
        return retrieval_service.retrieve(
            knowledge_base_id=selected_knowledge_base_id,
            query=state.get(
                "effective_question",
                state.get("resolved_question", state["question"]),
            ),
            top_k=state["top_k"],
        )

    settings = get_settings()
    return retrieval_service.retrieve_many(
        knowledge_base_ids=selected_kb_ids,
        query=state.get(
            "effective_question",
            state.get("resolved_question", state["question"]),
        ),
        top_k=state["top_k"],
        per_kb_top_k=settings.retrieval_per_kb_top_k,
    )


def _build_retrieval_trace_detail(
    *,
    state: ChatWorkflowState,
    citations: list[ChatCitation],
    retrieval_service: RetrievalService,
    kb_scope_label: str,
) -> str:
    retrieval_count = len(citations)
    best_score = max((citation.score for citation in citations), default=0.0)
    detail = (
        f"知识库范围 {kb_scope_label} 检索完成，命中 {retrieval_count} 条片段，"
        f"使用 {retrieval_service.describe_strategy()}，最高分 {best_score:.3f}。"
    )
    resolved_question = state.get("resolved_question", state["question"]).strip()
    effective_question = state.get("effective_question", resolved_question).strip()
    if effective_question != resolved_question:
        detail += f" 检索问题：{effective_question}"
    return detail


def _review_gate(state: ChatWorkflowState) -> ChatWorkflowState:
    assistant_config = state["assistant_config"]
    if not assistant_config.get("review_enabled", False):
        return {}

    if not state.get("citations"):
        return {
            "workflow_trace": _append_trace(
                state,
                node="review_gate",
                detail="助理已开启 review，但当前无检索命中，跳过人工复核路由。",
            )
        }

    review_hit = evaluate_review_hit(
        state.get("resolved_question", state["question"]),
        list(assistant_config.get("review_rules", [])),
    )
    if review_hit is None:
        return {
            "workflow_trace": _append_trace(
                state,
                node="review_gate",
                detail="助理已开启 review，本轮未命中人工复核规则，继续自动回答。",
            )
        }

    return {
        "fallback_reason": "review_required",
        "review_reason": review_hit.reason,
        "workflow_trace": _append_trace(
            state,
            node="review_gate",
            detail=f"已命中人工复核规则，暂停自动回答：{review_hit.reason}",
        ),
    }


def _format_review_note(reviewer_note: str) -> str:
    note = reviewer_note.strip()
    if not note:
        return ""
    return f" 审核意见：{note}"


def _review_hold(state: ChatWorkflowState) -> ChatWorkflowState:
    if state.get("fallback_reason") != "review_required":
        return {}

    resolved_question = state.get("resolved_question", state["question"])
    review_payload = interrupt(
        {
            "type": "review_required",
            "question": resolved_question,
            "review_reason": state.get("review_reason", ""),
            "selected_kb_ids": state.get("selected_kb_ids", []),
            "selected_knowledge_base_id": state.get("selected_knowledge_base_id", ""),
            "retrieval_count": state.get("retrieval_count", 0),
        }
    )
    if not isinstance(review_payload, dict):
        review_payload = {}

    action = str(review_payload.get("action", "approve")).strip() or "approve"
    reviewer_note = str(review_payload.get("reviewer_note", "")).strip()
    if action == "reject":
        manual_answer = build_review_rejected_answer(
            question=resolved_question,
            reviewer_note=reviewer_note,
            manual_answer=str(review_payload.get("manual_answer", "")).strip(),
        )
        return {
            "answer": manual_answer,
            "citations": [],
            "review_decision": "rejected",
            "fallback_reason": None,
            "workflow_trace": _append_trace(
                state,
                node="review_hold",
                detail=(
                    "人工审核未通过，当前问题已转为人工处理结论。"
                    f"{_format_review_note(reviewer_note)}"
                ),
            ),
        }

    return {
        "review_decision": "approved",
        "fallback_reason": None,
        "workflow_trace": _append_trace(
            state,
            node="review_hold",
            detail=(
                "人工审核已通过，恢复自动回答生成。"
                f"{_format_review_note(reviewer_note)}"
            ),
        ),
    }


def _retrieve_context(state: ChatWorkflowState) -> ChatWorkflowState:
    selected_kb_ids = state.get("selected_kb_ids", [])
    selected_knowledge_base_id = state["selected_knowledge_base_id"]
    retrieval_service = RetrievalService()
    citation_dicts = _retrieve_citation_dicts(
        state=state,
        retrieval_service=retrieval_service,
        selected_kb_ids=selected_kb_ids,
        selected_knowledge_base_id=selected_knowledge_base_id,
    )
    citations = [ChatCitation(**item) for item in citation_dicts]
    retrieval_count = len(citations)
    kb_scope_label = _format_kb_scope_label(
        selected_kb_ids=selected_kb_ids,
        selected_knowledge_base_id=selected_knowledge_base_id,
    )
    detail = _build_retrieval_trace_detail(
        state=state,
        citations=citations,
        retrieval_service=retrieval_service,
        kb_scope_label=kb_scope_label,
    )

    result: ChatWorkflowState = {
        "citations": citations,
        "retrieval_count": retrieval_count,
        "workflow_trace": _append_trace(
            state,
            node="retrieval",
            detail=detail,
        ),
    }
    return result


def _compose_answer(state: ChatWorkflowState) -> ChatWorkflowState:
    question = state["question"]
    resolved_question = state.get("resolved_question", question)
    citations = state.get("citations", [])
    assistant_name = state["assistant_name"]
    assistant_config = state["assistant_config"]
    selected_knowledge_base_id = state.get("selected_knowledge_base_id", "")
    selected_kb_ids = state.get("selected_kb_ids", [])
    fallback_reason = state.get("fallback_reason")
    review_reason = state.get("review_reason", "")

    if fallback_reason == "no_knowledge_base_selected":
        answer = build_no_knowledge_base_answer(
            assistant_name=assistant_name,
            question=resolved_question,
        )
        return {
            "answer": answer,
            "workflow_trace": _append_trace(
                state,
                node="compose_answer",
                detail="未进入检索，直接返回知识库范围缺失的兜底回答。",
            ),
        }

    if fallback_reason == "intent_clarification_required":
        answer = build_intent_clarification_answer(
            assistant_name=assistant_name,
            question=question,
            current_goal=state.get("current_goal", question),
            drift_reason=(
                state.get("clarification_reason", "").strip()
                or (
                    "当前问题与会话主线的相似度为 "
                    f"{1.0 - state.get('intent_drift_score', 0.0):.2f}"
                )
            ),
            clarification_type=state.get("clarification_type", "confirm_switch"),
        )
        return {
            "answer": answer,
            "workflow_trace": _append_trace(
                state,
                node="compose_answer",
                detail="检测到会话主线可能漂移，已返回澄清提示，不进入检索与回答生成。",
            ),
        }

    if not citations:
        answer = build_no_retrieval_hits_answer(
            assistant_name=assistant_name,
            question=resolved_question,
            selected_kb_ids=selected_kb_ids,
            selected_knowledge_base_id=selected_knowledge_base_id,
        )
        return {
            "answer": answer,
            "fallback_reason": None,
            "workflow_trace": _append_trace(
                state,
                node="compose_answer",
                detail="检索结果为空，返回无命中兜底回答。",
            ),
        }

    if fallback_reason == "review_required":
        answer = build_review_required_answer(
            assistant_name=assistant_name,
            question=resolved_question,
            review_reason=review_reason or "命中人工复核规则",
        )
        return {
            "answer": answer,
            "workflow_trace": _append_trace(
                state,
                node="compose_answer",
                detail=f"当前问题需要人工复核，未继续自动生成答案：{review_reason}",
            ),
        }

    generation_service = AnswerGenerationService()
    generated = generation_service.generate_answer(
        assistant_name=assistant_name,
        system_prompt=assistant_config.get("system_prompt", ""),
        question=resolved_question,
        effective_question=state.get("effective_question", resolved_question),
        current_goal=state.get("current_goal", resolved_question),
        memory_summary=state.get("memory_summary", ""),
        citations=citations,
        selected_kb_ids=selected_kb_ids,
        selected_knowledge_base_id=selected_knowledge_base_id,
        model_name=assistant_config.get("default_model", ""),
    )
    return {
        "answer": generated.content,
        "workflow_trace": _append_trace(
            state,
            node="compose_answer",
            detail=(
                f"已调用模型 {generated.model_name} 生成答案，"
                f"使用后端 {generated.backend_name}，"
                f"参考 {generated.citation_count} 条引用片段。"
            ),
        ),
        "fallback_reason": None,
    }


def _route_after_review_gate(
    state: ChatWorkflowState,
    *,
    include_compose_answer: bool,
) -> str:
    if (
        state.get("fallback_reason") == "review_required"
        and state.get("review_interrupt_enabled", False)
    ):
        return "review_hold"
    if include_compose_answer:
        return "compose_answer"
    return "end"


def _route_after_review_hold(
    state: ChatWorkflowState,
    *,
    include_compose_answer: bool,
) -> str:
    if state.get("review_decision") == "approved" and include_compose_answer:
        return "compose_answer"
    return "end"
