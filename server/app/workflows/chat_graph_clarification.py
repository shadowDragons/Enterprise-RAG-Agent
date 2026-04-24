from app.core.config import get_settings
from app.workflows.chat_graph_support import (
    _INTENT_GUARD_MIN_SIMILARITY,
    _INTENT_GUARD_MIN_TEXT_LENGTH,
    _STAY_ON_CURRENT_TOPIC_PREFIXES,
    _TOPIC_SWITCH_PREFIXES,
    ChatWorkflowState,
    _analyze_intent_similarity,
    _append_trace,
    _build_continue_current_topic_clarification,
    _build_current_topic_follow_up_resolution,
    _build_focus_drift_detail,
    _build_focus_drift_reason,
    _build_memory_summary,
    _build_new_topic_question_clarification,
    _extract_clarification_continuation_question,
    _looks_like_context_dependent_follow_up,
    _looks_like_continue_current_topic_confirmation,
    _looks_like_explicit_topic_switch,
    _looks_like_stay_on_current_topic,
    _looks_like_switch_confirmation,
    _normalize_intent_text,
    _resolve_clarification_stage,
    _resolve_current_goal,
    _resolve_effective_question,
    _resolve_pending_question,
    _split_prefixed_question,
)


def _load_assistant_config(state: ChatWorkflowState) -> ChatWorkflowState:
    assistant_config = state["assistant_config"]
    default_kb_ids = [
        kb_id for kb_id in assistant_config.get("default_kb_ids", []) if kb_id
    ]
    return {
        "assistant_id": assistant_config["assistant_id"],
        "assistant_name": assistant_config["assistant_name"],
        "selected_kb_ids": [],
        "workflow_trace": _append_trace(
            state,
            node="assistant_config",
            detail=(
                f"已加载助理“{assistant_config['assistant_name']}”配置，"
                f"默认知识库数量 {len(default_kb_ids)}。"
            ),
        ),
    }


def _resolve_kb_scope(state: ChatWorkflowState) -> ChatWorkflowState:
    settings = get_settings()
    assistant_config = state["assistant_config"]
    requested_kb_ids = list(
        dict.fromkeys(
            kb_id.strip()
            for kb_id in state.get("requested_knowledge_base_ids", [])
            if kb_id and kb_id.strip()
        )
    )
    default_kb_ids = [
        kb_id for kb_id in assistant_config.get("default_kb_ids", []) if kb_id
    ]
    selected_kb_ids = requested_kb_ids or default_kb_ids
    selected_kb_ids = selected_kb_ids[: settings.max_chat_selected_kb_count]
    selected_knowledge_base_id = selected_kb_ids[0] if selected_kb_ids else ""

    if selected_knowledge_base_id:
        joined_kb_ids = "、".join(selected_kb_ids)
        detail = f"本轮问答使用默认知识库范围：{joined_kb_ids}。"
        if requested_kb_ids:
            detail = f"本轮问答使用用户显式选择的知识库范围：{joined_kb_ids}。"
        return {
            "selected_knowledge_base_id": selected_knowledge_base_id,
            "selected_kb_ids": selected_kb_ids,
            "workflow_trace": _append_trace(
                state,
                node="kb_scope",
                detail=detail,
            ),
        }

    return {
        "selected_knowledge_base_id": "",
        "selected_kb_ids": [],
        "citations": [],
        "retrieval_count": 0,
        "fallback_reason": "no_knowledge_base_selected",
        "workflow_trace": _append_trace(
            state,
            node="kb_scope",
            detail="当前会话未显式选择知识库，助理也未配置默认知识库。",
        ),
    }


def _intake_question(state: ChatWorkflowState) -> ChatWorkflowState:
    raw_question = state["question"].strip()
    normalized_question = raw_question
    control_action = ""
    session_status = state.get("session_status", "active")

    if session_status == "awaiting_clarification":
        if _looks_like_stay_on_current_topic(raw_question):
            control_action = "continue_current_topic"
            _, normalized_question = _split_prefixed_question(
                raw_question,
                prefixes=_STAY_ON_CURRENT_TOPIC_PREFIXES,
            )
        else:
            rejected_switch, extracted_question = (
                _extract_clarification_continuation_question(raw_question)
            )
            if rejected_switch:
                control_action = "reject_switch"
                normalized_question = extracted_question
            elif _looks_like_continue_current_topic_confirmation(raw_question):
                control_action = "continue_current_topic"
                normalized_question = ""
            elif _looks_like_switch_confirmation(raw_question):
                control_action = "confirm_switch"
                normalized_question = ""
            elif _looks_like_explicit_topic_switch(raw_question):
                control_action = "explicit_switch"
                _, extracted_question = _split_prefixed_question(
                    raw_question,
                    prefixes=_TOPIC_SWITCH_PREFIXES,
                )
                normalized_question = extracted_question
    elif _looks_like_explicit_topic_switch(raw_question):
        control_action = "explicit_switch"
        _, extracted_question = _split_prefixed_question(
            raw_question,
            prefixes=_TOPIC_SWITCH_PREFIXES,
        )
        normalized_question = extracted_question

    detail = "当前问题无需做控制语义归一化，沿原始输入进入后续节点。"
    if control_action == "continue_current_topic":
        if normalized_question:
            detail = (
                "识别到继续原话题控制指令，"
                f"已提取具体问题“{normalized_question}”。"
            )
        else:
            detail = "识别到继续原话题控制指令，但当前尚未提供具体问题。"
    elif control_action == "reject_switch":
        if normalized_question:
            detail = (
                "识别到“不切换主题”控制指令，"
                f"已提取原话题追问“{normalized_question}”。"
            )
        else:
            detail = "识别到“不切换主题”控制指令，但当前尚未提供具体问题。"
    elif control_action == "confirm_switch":
        detail = "识别到切换主题确认指令，等待澄清恢复节点继续处理待确认问题。"
    elif control_action == "explicit_switch":
        if normalized_question:
            detail = (
                "识别到显式切换主题指令，"
                f"后续按问题“{normalized_question}”继续执行。"
            )
        else:
            detail = "识别到显式切换主题指令，但当前尚未提供新主题的具体问题。"

    return {
        "raw_question": raw_question,
        "normalized_question": normalized_question,
        "question_control_action": control_action,
        "workflow_trace": _append_trace(
            state,
            node="question_intake",
            detail=detail,
        ),
    }


def _manage_memory(state: ChatWorkflowState) -> ChatWorkflowState:
    settings = get_settings()
    history = [
        item
        for item in state.get("message_history", [])
        if item.get("content", "").strip()
    ][-settings.chat_memory_message_window :]
    raw_question = state.get("raw_question", state["question"]).strip()
    question = state.get("normalized_question", raw_question).strip()
    current_goal = _resolve_current_goal(
        history=history,
        question=question or raw_question,
        session_status=state.get("session_status", "active"),
        session_runtime_context=state.get("session_runtime_context"),
    )
    memory_summary = _build_memory_summary(history)
    effective_question = ""
    if question:
        effective_question = _resolve_effective_question(
            history=history,
            question=question,
            current_goal=current_goal,
        )
    detail = f"已整理最近 {len(history)} 条历史消息，当前目标“{current_goal}”。"
    if not question and raw_question:
        detail += " 当前输入主要是控制指令，等待澄清恢复节点决定下一步。"
    elif effective_question != question:
        detail += f" 检索问题已改写为：{effective_question}"
    else:
        detail += " 当前问题足够明确，直接用于检索。"

    return {
        "current_goal": current_goal,
        "resolved_question": question,
        "memory_summary": memory_summary,
        "effective_question": effective_question,
        "workflow_trace": _append_trace(
            state,
            node="memory_manager",
            detail=detail,
        ),
    }


def _clarification_router(state: ChatWorkflowState) -> ChatWorkflowState:
    session_status = state.get("session_status", "active")
    if session_status != "awaiting_clarification":
        return {
            "clarification_route": "clarification_passthrough",
            "workflow_trace": _append_trace(
                state,
                node="clarification_router",
                detail="当前会话不处于待澄清状态，跳过澄清状态机。",
            ),
        }

    question_control_action = str(state.get("question_control_action", "")).strip()
    clarification_stage = _resolve_clarification_stage(state)

    if question_control_action in {"continue_current_topic", "reject_switch"}:
        return {
            "clarification_route": "clarification_current_topic",
            "workflow_trace": _append_trace(
                state,
                node="clarification_router",
                detail="当前处于待澄清状态，且用户已表达继续原话题，进入原主线恢复分支。",
            ),
        }
    if (
        question_control_action == "explicit_switch"
        or clarification_stage == "collect_new_topic_question"
    ):
        return {
            "clarification_route": "clarification_new_topic",
            "workflow_trace": _append_trace(
                state,
                node="clarification_router",
                detail="当前处于待澄清状态，且用户要切换到新主题，进入新主题恢复分支。",
            ),
        }
    if (
        question_control_action == "confirm_switch"
        or clarification_stage == "confirm_switch"
    ):
        return {
            "clarification_route": "clarification_confirm_switch",
            "workflow_trace": _append_trace(
                state,
                node="clarification_router",
                detail="当前处于待澄清状态，进入切题确认分支。",
            ),
        }
    return {
        "clarification_route": "clarification_freeform_router",
        "workflow_trace": _append_trace(
            state,
            node="clarification_router",
            detail="当前处于待澄清状态，但未命中显式控制指令，进入 freeform 澄清分类分支。",
        ),
    }


def _clarification_passthrough(state: ChatWorkflowState) -> ChatWorkflowState:
    del state
    return {
        "clarification_action": "skip",
    }


def _clarification_confirm_switch(state: ChatWorkflowState) -> ChatWorkflowState:
    history = state.get("message_history", [])
    pending_question = _resolve_pending_question(
        history=history,
        session_status=state.get("session_status", "active"),
        session_runtime_context=state.get("session_runtime_context"),
    )
    question_control_action = str(state.get("question_control_action", "")).strip()
    if pending_question and question_control_action == "confirm_switch":
        return {
            "current_goal": pending_question,
            "resolved_question": pending_question,
            "effective_question": pending_question,
            "clarification_action": "resume_pending_topic",
            "intent_action": "switch_topic",
            "intent_drift_score": 0.0,
            "workflow_trace": _append_trace(
                state,
                node="clarification_confirm_switch",
                detail=(
                    "上一轮已请求澄清，用户已确认切换主题，"
                    f"本轮沿待确认问题“{pending_question}”继续执行。"
                ),
            ),
        }

    return {
        "clarification_action": "defer_to_clarification_freeform",
    }


def _clarification_current_topic(state: ChatWorkflowState) -> ChatWorkflowState:
    raw_question = state.get("raw_question", state["question"]).strip()
    question = state.get("normalized_question", raw_question).strip()
    current_goal = state.get("current_goal", question or raw_question).strip()
    history = state.get("message_history", [])
    question_control_action = str(state.get("question_control_action", "")).strip()

    if question_control_action == "continue_current_topic":
        if question:
            return _build_current_topic_follow_up_resolution(
                state=state,
                current_goal=current_goal,
                question=question,
                history=history,
                detail=(
                    "上一轮已请求澄清，用户已明确表示继续原主线，"
                    f"并补充本轮问题“{question}”。"
                ),
                trace_node="clarification_current_topic",
            )
        return _build_continue_current_topic_clarification(
            state=state,
            current_goal=current_goal,
            detail="上一轮已请求澄清，用户表示继续原主线，但尚未给出新的具体问题。",
            trace_node="clarification_current_topic",
        )

    if question:
        return _build_current_topic_follow_up_resolution(
            state=state,
            current_goal=current_goal,
            question=question,
            history=history,
            detail=(
                "上一轮已请求澄清，用户已明确表示不切换主题，"
                f"并改为继续原主线问题“{question}”。"
            ),
            trace_node="clarification_current_topic",
        )
    return _build_continue_current_topic_clarification(
        state=state,
        current_goal=current_goal,
        detail=(
            "上一轮已请求澄清，用户已明确表示不切换主题，"
            "但当前回复还不足以形成可执行问题。"
        ),
        trace_node="clarification_current_topic",
    )


def _clarification_new_topic(state: ChatWorkflowState) -> ChatWorkflowState:
    raw_question = state.get("raw_question", state["question"]).strip()
    question = state.get("normalized_question", raw_question).strip()
    current_goal = state.get("current_goal", question or raw_question).strip()
    clarification_stage = _resolve_clarification_stage(state)

    if clarification_stage == "collect_new_topic_question":
        if question:
            return {
                "current_goal": question,
                "resolved_question": question,
                "effective_question": question,
                "clarification_action": "switch_to_new_topic",
                "intent_action": "switch_topic",
                "intent_drift_score": 0.0,
                "workflow_trace": _append_trace(
                    state,
                    node="clarification_new_topic",
                    detail=(
                        "上一轮已确认准备切换主题，"
                        f"用户现已补充新问题“{question}”，本轮按新主题继续执行。"
                    ),
                ),
            }
        return _build_new_topic_question_clarification(
            state=state,
            current_goal=current_goal,
            detail="上一轮已确认准备切换主题，但当前仍未提供新主题的具体问题。",
            trace_node="clarification_new_topic",
        )

    if not question:
        return _build_new_topic_question_clarification(
            state=state,
            current_goal=current_goal,
            detail=(
                "上一轮已请求澄清，用户这次明确表示要切换主题，"
                "但仍未提供新主题的具体问题。"
            ),
            trace_node="clarification_new_topic",
        )
    resolved_question = question or raw_question
    return {
        "current_goal": resolved_question,
        "resolved_question": resolved_question,
        "effective_question": resolved_question,
        "clarification_action": "switch_to_new_topic",
        "intent_action": "switch_topic",
        "intent_drift_score": 0.0,
        "workflow_trace": _append_trace(
            state,
            node="clarification_new_topic",
            detail=(
                "上一轮已请求澄清，用户这次已明确给出新主题，"
                f"本轮按问题“{resolved_question}”继续执行。"
            ),
        ),
    }


def _clarification_freeform_router(state: ChatWorkflowState) -> ChatWorkflowState:
    raw_question = state.get("raw_question", state["question"]).strip()
    question = state.get("normalized_question", raw_question).strip()
    current_goal = state.get("current_goal", question or raw_question).strip()

    if _looks_like_context_dependent_follow_up(question):
        return {
            "clarification_freeform_route": "clarification_freeform_current_topic",
            "workflow_trace": _append_trace(
                state,
                node="clarification_freeform_router",
                detail="待澄清 freeform 回复呈现连续追问特征，进入原主线恢复分支。",
            ),
        }

    normalized_question = _normalize_intent_text(question)
    normalized_goal = _normalize_intent_text(current_goal)
    if (
        len(normalized_question) >= _INTENT_GUARD_MIN_TEXT_LENGTH
        and len(normalized_goal) >= _INTENT_GUARD_MIN_TEXT_LENGTH
    ):
        (
            similarity,
            focus_similarity,
            goal_focus,
            question_focus,
            template_overlap_drift,
        ) = _analyze_intent_similarity(current_goal, question)
        if similarity < _INTENT_GUARD_MIN_SIMILARITY or template_overlap_drift:
            detail = "待澄清 freeform 回复已形成新的明确问题，进入新主题恢复分支。"
            if template_overlap_drift:
                detail = (
                    "待澄清 freeform 回复虽然沿用了相似问句模板，"
                    f"但主题核心已从“{goal_focus}”切到“{question_focus}”，"
                    f"整体相似度 {similarity:.2f}，进入新主题恢复分支。"
                )
            else:
                detail = f"{detail} 当前与原主线相似度 {similarity:.2f}。"
            return {
                "clarification_freeform_route": "clarification_freeform_new_topic",
                "workflow_trace": _append_trace(
                    state,
                    node="clarification_freeform_router",
                    detail=detail,
                ),
            }

        return {
            "clarification_freeform_route": "clarification_freeform_current_topic",
            "workflow_trace": _append_trace(
                state,
                node="clarification_freeform_router",
                detail=(
                    "待澄清 freeform 回复已经把需求补充得更明确，"
                    f"与原主线相似度 {similarity:.2f}，进入原主线恢复分支。"
                ),
            ),
        }

    return {
        "clarification_freeform_route": "clarification_freeform_defer",
        "workflow_trace": _append_trace(
            state,
            node="clarification_freeform_router",
            detail="待澄清 freeform 回复仍不够明确，回退给意图守卫做最后判断。",
        ),
    }


def _clarification_freeform_current_topic(state: ChatWorkflowState) -> ChatWorkflowState:
    raw_question = state.get("raw_question", state["question"]).strip()
    question = state.get("normalized_question", raw_question).strip()
    current_goal = state.get("current_goal", question or raw_question).strip()
    history = state.get("message_history", [])

    if _looks_like_context_dependent_follow_up(question):
        return _build_current_topic_follow_up_resolution(
            state=state,
            current_goal=current_goal,
            question=question,
            history=history,
            detail="上一轮处于等待澄清状态，当前回复表明用户仍要沿原主线继续追问。",
            trace_node="clarification_freeform_current_topic",
        )

    similarity, _, _, _, _ = _analyze_intent_similarity(current_goal, question)
    return {
        "current_goal": question,
        "resolved_question": question,
        "effective_question": question,
        "clarification_action": "resume_current_topic",
        "intent_action": "continue",
        "intent_drift_score": 1.0 - similarity,
        "workflow_trace": _append_trace(
            state,
            node="clarification_freeform_current_topic",
            detail=(
                "上一轮已请求澄清，当前回复已经把需求补充得更明确，"
                f"与原主线相似度 {similarity:.2f}，本轮直接按该问题继续执行。"
            ),
        ),
    }


def _clarification_freeform_new_topic(state: ChatWorkflowState) -> ChatWorkflowState:
    raw_question = state.get("raw_question", state["question"]).strip()
    question = state.get("normalized_question", raw_question).strip()
    similarity, focus_similarity, goal_focus, question_focus, template_overlap_drift = (
        _analyze_intent_similarity(
            state.get("current_goal", question or raw_question).strip(),
            question,
        )
    )
    detail = (
        "上一轮已请求澄清，当前回复已形成新的明确问题，"
        f"与原主线相似度 {similarity:.2f}，本轮按新主题继续执行。"
    )
    if template_overlap_drift:
        detail = (
            "上一轮已请求澄清，当前回复虽然沿用了相似问句模板，"
            f"但主题核心已从“{goal_focus}”切到“{question_focus}”，"
            f"整体相似度 {similarity:.2f}。"
        )
        focus_detail = _build_focus_drift_detail(
            goal_focus=goal_focus,
            question_focus=question_focus,
            focus_similarity=focus_similarity,
        )
        if focus_detail:
            detail += f" {focus_detail}。"
        detail += " 本轮按新主题继续执行。"

    return {
        "current_goal": question,
        "resolved_question": question,
        "effective_question": question,
        "clarification_action": "switch_to_new_topic",
        "intent_action": "switch_topic",
        "intent_drift_score": 1.0 - similarity,
        "workflow_trace": _append_trace(
            state,
            node="clarification_freeform_new_topic",
            detail=detail,
        ),
    }


def _clarification_freeform_defer(state: ChatWorkflowState) -> ChatWorkflowState:
    return {
        "clarification_action": "defer_to_intent_guard",
        "workflow_trace": _append_trace(
            state,
            node="clarification_freeform_defer",
            detail="当前回复未命中可直接恢复的澄清规则，继续交给意图守卫判断。",
        ),
    }


def _intent_guard(state: ChatWorkflowState) -> ChatWorkflowState:
    raw_question = state.get("raw_question", state["question"]).strip()
    normalized_question = state.get("normalized_question", raw_question).strip()
    question = normalized_question or raw_question
    current_goal = state.get("current_goal", question).strip()
    history = state.get("message_history", [])
    question_control_action = str(state.get("question_control_action", "")).strip()

    if question_control_action == "explicit_switch":
        if not normalized_question:
            return _build_new_topic_question_clarification(
                state=state,
                current_goal=current_goal,
                detail="用户已明确表示要切换主题，但还没有给出新主题的具体问题。",
            )
        resolved_question = question or raw_question
        detail = "用户已明确声明切换到新话题，本轮按新问题继续执行。"
        if question:
            detail = (
                "用户已明确声明切换到新话题，"
                f"本轮按问题“{resolved_question}”继续执行。"
            )
        return {
            "current_goal": resolved_question,
            "resolved_question": resolved_question,
            "effective_question": resolved_question,
            "intent_action": "switch_topic",
            "intent_drift_score": 0.0,
            "workflow_trace": _append_trace(
                state,
                node="intent_guard",
                detail=detail,
            ),
        }

    if not history or current_goal == question:
        return {
            "intent_action": "continue",
            "intent_drift_score": 0.0,
            "workflow_trace": _append_trace(
                state,
                node="intent_guard",
                detail="当前没有足够历史主线信息，跳过意图漂移检测。",
            ),
        }

    if _looks_like_context_dependent_follow_up(question):
        return {
            "intent_action": "continue",
            "intent_drift_score": 0.0,
            "workflow_trace": _append_trace(
                state,
                node="intent_guard",
                detail="当前问题呈现连续追问特征，继续沿当前会话主线执行。",
            ),
        }

    if (
        len(_normalize_intent_text(question)) < _INTENT_GUARD_MIN_TEXT_LENGTH
        or len(_normalize_intent_text(current_goal)) < _INTENT_GUARD_MIN_TEXT_LENGTH
    ):
        return {
            "intent_action": "continue",
            "intent_drift_score": 0.0,
            "workflow_trace": _append_trace(
                state,
                node="intent_guard",
                detail="当前问题或主线过短，暂不触发意图漂移澄清。",
            ),
        }

    (
        similarity,
        focus_similarity,
        goal_focus,
        question_focus,
        template_overlap_drift,
    ) = _analyze_intent_similarity(current_goal, question)
    drift_score = 1.0 - similarity
    if similarity < _INTENT_GUARD_MIN_SIMILARITY or template_overlap_drift:
        detail = (
            f"检测到当前问题可能偏离会话主线，"
            f"主线“{current_goal}”，相似度 {similarity:.2f}，"
        )
        clarification_reason = "当前问题与原主线相关性较弱，需要确认是否切换主题。"
        if template_overlap_drift:
            clarification_reason = _build_focus_drift_reason(
                goal_focus=goal_focus,
                question_focus=question_focus,
            )
            focus_detail = _build_focus_drift_detail(
                goal_focus=goal_focus,
                question_focus=question_focus,
                focus_similarity=focus_similarity,
            )
            if focus_detail:
                detail += f"{focus_detail}，"
        detail += "先请求用户确认是否切换主题。"
        return {
            "intent_action": "clarify",
            "intent_drift_score": drift_score,
            "clarification_type": "confirm_switch",
            "clarification_stage": "confirm_switch",
            "clarification_expected_input": "topic_switch_confirmation",
            "clarification_reason": clarification_reason,
            "fallback_reason": "intent_clarification_required",
            "citations": [],
            "retrieval_count": 0,
            "workflow_trace": _append_trace(
                state,
                node="intent_guard",
                detail=detail,
            ),
        }

    return {
        "intent_action": "continue",
        "intent_drift_score": drift_score,
        "workflow_trace": _append_trace(
            state,
            node="intent_guard",
            detail=(
                f"当前问题与会话主线仍保持相关，相似度 {similarity:.2f}，"
                "继续进入检索阶段。"
            ),
        ),
    }


def _route_after_clarification_router(state: ChatWorkflowState) -> str:
    return str(state.get("clarification_route", "")).strip() or "clarification_passthrough"


def _route_after_clarification_freeform_router(state: ChatWorkflowState) -> str:
    return (
        str(state.get("clarification_freeform_route", "")).strip()
        or "clarification_freeform_defer"
    )


def _route_after_clarification_handler(
    state: ChatWorkflowState,
    *,
    include_compose_answer: bool,
) -> str:
    if state.get("clarification_action") == "defer_to_clarification_freeform":
        return "clarification_freeform_router"
    if state.get("fallback_reason") == "intent_clarification_required":
        if include_compose_answer:
            return "compose_answer"
        return "end"

    clarification_action = str(state.get("clarification_action", "")).strip()
    if clarification_action in {
        "resume_current_topic",
        "resume_pending_topic",
        "switch_to_new_topic",
    }:
        if state.get("selected_knowledge_base_id"):
            return "retrieve_context"
        if include_compose_answer:
            return "compose_answer"
        return "end"

    return "intent_guard"


def _route_after_intent_guard(
    state: ChatWorkflowState,
    *,
    include_compose_answer: bool,
) -> str:
    if state.get("fallback_reason") == "intent_clarification_required":
        if include_compose_answer:
            return "compose_answer"
        return "end"
    if state.get("selected_knowledge_base_id"):
        return "retrieve_context"
    if include_compose_answer:
        return "compose_answer"
    return "end"
