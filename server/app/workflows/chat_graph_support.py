from typing import TypedDict

from app.schemas.chat import ChatCitation, WorkflowTraceStep
from app.services.workflow_runtime import resolve_clarification_stage_from_runtime_state

_INTENT_GUARD_MIN_SIMILARITY = 0.18
_INTENT_GUARD_MIN_FOCUS_SIMILARITY = 0.18
_INTENT_GUARD_MIN_TEXT_LENGTH = 6
_CONTROL_PREFIX_DELIMITERS = "：:，,；; "
_INTENT_GUARD_GENERIC_SEGMENTS = (
    "需要什么材料",
    "需要哪些材料",
    "需要什么条件",
    "需要哪些条件",
    "最晚什么时候提交",
    "最晚什么时候提",
    "什么时候提交",
    "什么时候申请",
    "怎么申请",
    "如何申请",
    "申请流程",
    "审批流程",
    "需要什么",
    "需要哪些",
    "怎么处理",
    "怎么操作",
    "怎么办",
    "怎么做",
    "做什么",
    "什么材料",
    "哪些材料",
    "什么条件",
    "哪些条件",
    "什么要求",
    "哪些要求",
    "多少天",
    "什么时候",
    "注意事项",
    "办理流程",
    "流程",
    "步骤",
    "要求",
    "规定",
    "材料",
    "条件",
    "员工",
    "公司",
    "部门",
    "需要",
    "申请",
    "审批",
    "提交",
    "办理",
    "处理",
    "操作",
    "多久",
    "怎么",
    "如何",
    "怎样",
    "什么",
    "哪些",
    "一下",
    "请问",
    "吗",
    "呢",
    "呀",
    "吧",
)
_TOPIC_SWITCH_PREFIXES = (
    "切换到新问题",
    "换一个问题",
    "换个问题",
    "另一个问题",
    "切换话题",
    "切换到",
    "新问题",
    "新话题",
    "另外问",
)
_STAY_ON_CURRENT_TOPIC_PREFIXES = (
    "继续当前话题",
    "继续原话题",
    "继续这个话题",
    "继续刚才的话题",
    "不换话题",
    "不切换话题",
    "先不切换",
    "不切换",
)
_CLARIFICATION_REJECT_PREFIXES = (
    "不是",
    "不切换",
    "不用切换",
    "先不切换",
    "别切换",
    "不换话题",
)
_CLARIFICATION_REJECT_FILLER_PREFIXES = (
    "我是想继续问",
    "我想继续问",
    "我是想问",
    "我想问",
    "继续当前话题",
    "继续原话题",
    "继续这个话题",
    "继续问",
)
_CONTINUE_CURRENT_TOPIC_CONFIRMATIONS = {
    "继续",
    "继续吧",
    "继续当前话题",
    "继续原话题",
    "继续这个话题",
    "按原话题",
    "还是原话题",
    "就原话题",
}


class AssistantRuntimeConfig(TypedDict):
    assistant_id: str
    assistant_name: str
    system_prompt: str
    default_model: str
    default_kb_ids: list[str]
    review_rules: list[dict]
    review_enabled: bool


class ChatHistoryMessage(TypedDict):
    role: str
    content: str


class SessionRuntimeContext(TypedDict, total=False):
    current_goal: str
    pending_question: str
    resolved_question: str
    clarification_type: str
    clarification_stage: str
    clarification_expected_input: str
    clarification_reason: str


class ChatWorkflowState(TypedDict, total=False):
    assistant_id: str
    assistant_name: str
    assistant_config: AssistantRuntimeConfig
    session_status: str
    session_runtime_context: SessionRuntimeContext
    session_runtime_state: str
    question: str
    raw_question: str
    normalized_question: str
    question_control_action: str
    resolved_question: str
    message_history: list[ChatHistoryMessage]
    current_goal: str
    effective_question: str
    memory_summary: str
    intent_action: str
    intent_drift_score: float
    clarification_route: str
    clarification_action: str
    clarification_freeform_route: str
    clarification_type: str
    clarification_stage: str
    clarification_expected_input: str
    clarification_reason: str
    review_interrupt_enabled: bool
    review_reason: str
    review_decision: str
    requested_knowledge_base_ids: list[str]
    selected_knowledge_base_id: str
    selected_kb_ids: list[str]
    top_k: int
    citations: list[ChatCitation]
    retrieval_count: int
    answer: str
    fallback_reason: str | None
    workflow_trace: list[WorkflowTraceStep]


def _append_trace(
    state: ChatWorkflowState,
    *,
    node: str,
    detail: str,
) -> list[WorkflowTraceStep]:
    trace = list(state.get("workflow_trace", []))
    trace.append(WorkflowTraceStep(node=node, detail=detail))
    return trace


def _resolve_current_goal(
    *,
    history: list[ChatHistoryMessage],
    question: str,
    session_status: str = "active",
    session_runtime_context: SessionRuntimeContext | None = None,
) -> str:
    context = session_runtime_context or {}
    if session_status == "awaiting_clarification":
        context_current_goal = str(context.get("current_goal", "")).strip()
        if context_current_goal:
            return context_current_goal
        return question

    previous_user_messages = _previous_user_messages(history)
    if previous_user_messages:
        return previous_user_messages[-1]
    return question


def _previous_user_messages(history: list[ChatHistoryMessage]) -> list[str]:
    return [
        item["content"].strip()
        for item in history
        if item.get("role") == "user" and item.get("content", "").strip()
    ]


def _build_memory_summary(history: list[ChatHistoryMessage]) -> str:
    if not history:
        return ""

    lines: list[str] = []
    for item in history[-4:]:
        role_label = "用户" if item.get("role") == "user" else "助手"
        content = item.get("content", "").replace("\n", " ").strip()
        if len(content) > 80:
            content = f"{content[:80]}..."
        lines.append(f"{role_label}：{content}")
    return "\n".join(lines)


def _resolve_effective_question(
    *,
    history: list[ChatHistoryMessage],
    question: str,
    current_goal: str,
) -> str:
    if not history:
        return question
    if not _looks_like_follow_up(question):
        return question
    if current_goal.strip() == question.strip():
        return question
    return f"上一轮问题：{current_goal}\n当前追问：{question}"


def _looks_like_follow_up(question: str) -> bool:
    normalized_question = question.strip()
    if len(normalized_question) <= 12:
        return True
    return normalized_question.startswith(
        (
            "那",
            "那么",
            "这个",
            "这个问题",
            "它",
            "还",
            "还有",
            "另外",
            "再",
            "然后",
            "继续",
            "补充",
            "那如果",
            "那报销",
            "那请假",
        )
    )


def _looks_like_context_dependent_follow_up(question: str) -> bool:
    normalized_question = question.strip()
    if normalized_question.startswith(
        (
            "那",
            "那么",
            "这个",
            "这个问题",
            "它",
            "还",
            "还有",
            "另外",
            "再",
            "然后",
            "继续",
            "补充",
            "那如果",
            "那报销",
            "那请假",
        )
    ):
        return True
    return any(
        marker in normalized_question
        for marker in ("这个", "那个", "上述", "上面", "刚才", "前面", "这件事")
    )


def _format_kb_scope_label(
    *,
    selected_kb_ids: list[str],
    selected_knowledge_base_id: str,
) -> str:
    if selected_kb_ids:
        return "、".join(selected_kb_ids)
    return selected_knowledge_base_id


def _looks_like_explicit_topic_switch(question: str) -> bool:
    normalized_question = question.strip()
    return normalized_question.startswith(_TOPIC_SWITCH_PREFIXES)


def _split_prefixed_question(
    question: str,
    *,
    prefixes: tuple[str, ...],
) -> tuple[bool, str]:
    normalized_question = question.strip()
    for prefix in prefixes:
        if not normalized_question.startswith(prefix):
            continue
        remainder = normalized_question[len(prefix) :].strip()
        remainder = remainder.lstrip(_CONTROL_PREFIX_DELIMITERS).strip()
        return True, remainder
    return False, normalized_question


def _looks_like_stay_on_current_topic(question: str) -> bool:
    normalized_question = question.strip()
    return normalized_question.startswith(_STAY_ON_CURRENT_TOPIC_PREFIXES)


def _extract_clarification_continuation_question(question: str) -> tuple[bool, str]:
    remainder = question.strip()
    rejected_switch = False
    while True:
        matched, updated_remainder = _split_prefixed_question(
            remainder,
            prefixes=_CLARIFICATION_REJECT_PREFIXES,
        )
        if not matched:
            break
        rejected_switch = True
        remainder = updated_remainder.strip()

    if not rejected_switch:
        return False, question.strip()

    if not remainder:
        return True, ""

    while True:
        stripped_filler, extracted_question = _split_prefixed_question(
            remainder,
            prefixes=_CLARIFICATION_REJECT_FILLER_PREFIXES,
        )
        if not stripped_filler:
            break
        remainder = extracted_question.strip()
        if not remainder:
            return True, ""

    if not _normalize_intent_text(remainder):
        return True, ""
    if _looks_like_continue_current_topic_confirmation(remainder):
        return True, ""
    return True, remainder.strip()


def _looks_like_switch_confirmation(question: str) -> bool:
    normalized_question = _normalize_confirmation_text(question)
    return normalized_question in {
        "是",
        "是的",
        "对",
        "对的",
        "嗯",
        "好的",
        "好",
        "行",
        "确认",
        "确认切换",
        "切换",
        "切换吧",
        "换吧",
    }


def _normalize_confirmation_text(question: str) -> str:
    return (
        question.strip()
        .removesuffix("。")
        .removesuffix("！")
        .removesuffix("!")
        .removesuffix("？")
        .removesuffix("?")
        .strip()
    )


def _looks_like_continue_current_topic_confirmation(question: str) -> bool:
    return _normalize_confirmation_text(question) in _CONTINUE_CURRENT_TOPIC_CONFIRMATIONS


def _normalize_intent_text(text: str) -> str:
    return "".join(
        character.lower()
        for character in text
        if character.isalnum() or "\u4e00" <= character <= "\u9fff"
    )


def _extract_bigrams(text: str) -> set[str]:
    normalized = _normalize_intent_text(text)
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[index : index + 2] for index in range(len(normalized) - 1)}


def _calculate_text_similarity(left_text: str, right_text: str) -> float:
    left_bigrams = _extract_bigrams(left_text)
    right_bigrams = _extract_bigrams(right_text)
    if not left_bigrams or not right_bigrams:
        return 0.0
    overlap = left_bigrams & right_bigrams
    union = left_bigrams | right_bigrams
    return len(overlap) / len(union)


def _calculate_intent_similarity(current_goal: str, question: str) -> float:
    return _calculate_text_similarity(current_goal, question)


def _extract_intent_focus_text(text: str) -> str:
    focus_text = _normalize_intent_text(text)
    if not focus_text:
        return ""

    for segment in _INTENT_GUARD_GENERIC_SEGMENTS:
        normalized_segment = _normalize_intent_text(segment)
        if not normalized_segment:
            continue
        focus_text = focus_text.replace(normalized_segment, "")

    return focus_text.strip()


def _analyze_intent_similarity(
    current_goal: str,
    question: str,
) -> tuple[float, float | None, str, str, bool]:
    similarity = _calculate_intent_similarity(current_goal, question)
    goal_focus = _extract_intent_focus_text(current_goal)
    question_focus = _extract_intent_focus_text(question)
    if len(goal_focus) < 2 or len(question_focus) < 2:
        return similarity, None, goal_focus, question_focus, False

    focus_similarity = _calculate_text_similarity(goal_focus, question_focus)
    template_overlap_drift = (
        similarity >= _INTENT_GUARD_MIN_SIMILARITY
        and focus_similarity < _INTENT_GUARD_MIN_FOCUS_SIMILARITY
        and goal_focus != question_focus
    )
    return (
        similarity,
        focus_similarity,
        goal_focus,
        question_focus,
        template_overlap_drift,
    )


def _build_focus_drift_detail(
    *,
    goal_focus: str,
    question_focus: str,
    focus_similarity: float | None,
) -> str:
    if (
        focus_similarity is None
        or len(goal_focus) < 2
        or len(question_focus) < 2
        or goal_focus == question_focus
    ):
        return ""
    return (
        f"去掉通用问句模板后，主题核心分别为“{goal_focus}”与“{question_focus}”，"
        f"核心相似度 {focus_similarity:.2f}"
    )


def _build_focus_drift_reason(
    *,
    goal_focus: str,
    question_focus: str,
) -> str:
    if len(goal_focus) < 2 or len(question_focus) < 2 or goal_focus == question_focus:
        return "当前问题与原主线相关性较弱，需要确认是否切换主题。"
    return (
        "当前问题和原主线共用了相似问句模板，"
        f"但主题核心已从“{goal_focus}”切到“{question_focus}”，需要确认是否切换主题。"
    )


def _resolve_pending_question(
    *,
    history: list[ChatHistoryMessage],
    session_status: str,
    session_runtime_context: SessionRuntimeContext | None = None,
) -> str:
    del history
    if session_status != "awaiting_clarification":
        return ""
    context = session_runtime_context or {}
    return str(context.get("pending_question", "")).strip()


def _build_continue_current_topic_clarification(
    *,
    state: ChatWorkflowState,
    current_goal: str,
    detail: str,
    trace_node: str = "intent_guard",
) -> ChatWorkflowState:
    return {
        "current_goal": current_goal,
        "resolved_question": "",
        "effective_question": "",
        "clarification_action": "wait_for_follow_up_question",
        "clarification_type": "continue_current_topic",
        "clarification_stage": "collect_current_topic_question",
        "clarification_expected_input": "follow_up_question",
        "clarification_reason": "用户已表示继续原主线，但尚未给出可执行的具体追问。",
        "intent_action": "clarify",
        "intent_drift_score": 0.0,
        "fallback_reason": "intent_clarification_required",
        "citations": [],
        "retrieval_count": 0,
        "workflow_trace": _append_trace(
            state,
            node=trace_node,
            detail=detail,
        ),
    }


def _build_new_topic_question_clarification(
    *,
    state: ChatWorkflowState,
    current_goal: str,
    detail: str,
    trace_node: str = "intent_guard",
) -> ChatWorkflowState:
    return {
        "current_goal": current_goal,
        "resolved_question": "",
        "effective_question": "",
        "clarification_action": "wait_for_new_topic_question",
        "clarification_type": "new_topic_question",
        "clarification_stage": "collect_new_topic_question",
        "clarification_expected_input": "new_topic_question",
        "clarification_reason": "用户已明确表示要切换主题，但尚未给出新主题的具体问题。",
        "intent_action": "clarify",
        "intent_drift_score": 0.0,
        "fallback_reason": "intent_clarification_required",
        "citations": [],
        "retrieval_count": 0,
        "workflow_trace": _append_trace(
            state,
            node=trace_node,
            detail=detail,
        ),
    }


def _resolve_clarification_stage(state: ChatWorkflowState) -> str:
    runtime_stage = resolve_clarification_stage_from_runtime_state(
        str(state.get("session_runtime_state", "")).strip()
    )
    if runtime_stage:
        return runtime_stage

    context = state.get("session_runtime_context") or {}
    context_stage = str(context.get("clarification_stage", "")).strip()
    if context_stage:
        return context_stage

    return str(state.get("clarification_stage", "")).strip() or "confirm_switch"


def _build_current_topic_follow_up_resolution(
    *,
    state: ChatWorkflowState,
    current_goal: str,
    question: str,
    history: list[ChatHistoryMessage],
    detail: str,
    trace_node: str = "intent_guard",
) -> ChatWorkflowState:
    resolved_question = question.strip()
    effective_question = resolved_question
    if _looks_like_context_dependent_follow_up(resolved_question):
        effective_question = _resolve_effective_question(
            history=history,
            question=resolved_question,
            current_goal=current_goal,
        )
        if effective_question != resolved_question:
            detail += f" 检索问题已改写为：{effective_question}"

    return {
        "current_goal": resolved_question,
        "resolved_question": resolved_question,
        "effective_question": effective_question,
        "clarification_action": "resume_current_topic",
        "intent_action": "continue",
        "intent_drift_score": 0.0,
        "workflow_trace": _append_trace(
            state,
            node=trace_node,
            detail=detail,
        ),
    }
