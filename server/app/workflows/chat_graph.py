from langgraph.graph import END, START, StateGraph

from app.workflows.chat_graph_clarification import (
    _clarification_confirm_switch,
    _clarification_current_topic,
    _clarification_freeform_current_topic,
    _clarification_freeform_defer,
    _clarification_freeform_new_topic,
    _clarification_freeform_router,
    _clarification_new_topic,
    _clarification_passthrough,
    _clarification_router,
    _intent_guard,
    _intake_question,
    _load_assistant_config,
    _manage_memory,
    _resolve_kb_scope,
    _route_after_clarification_freeform_router,
    _route_after_clarification_handler,
    _route_after_clarification_router,
    _route_after_intent_guard,
)
from app.workflows.chat_graph_execution import (
    _compose_answer,
    _retrieve_context,
    _review_gate,
    _review_hold,
    _route_after_review_gate,
    _route_after_review_hold,
)
from app.workflows.chat_graph_support import ChatWorkflowState

_WORKFLOW_NODES = (
    ("assistant_config", _load_assistant_config),
    ("kb_scope", _resolve_kb_scope),
    ("question_intake", _intake_question),
    ("memory_manager", _manage_memory),
    ("clarification_router", _clarification_router),
    ("clarification_passthrough", _clarification_passthrough),
    ("clarification_confirm_switch", _clarification_confirm_switch),
    ("clarification_current_topic", _clarification_current_topic),
    ("clarification_new_topic", _clarification_new_topic),
    ("clarification_freeform_router", _clarification_freeform_router),
    (
        "clarification_freeform_current_topic",
        _clarification_freeform_current_topic,
    ),
    ("clarification_freeform_new_topic", _clarification_freeform_new_topic),
    ("clarification_freeform_defer", _clarification_freeform_defer),
    ("intent_guard", _intent_guard),
    ("retrieve_context", _retrieve_context),
    ("review_gate", _review_gate),
    ("review_hold", _review_hold),
)

_CLARIFICATION_HANDLER_NODE_NAMES = (
    "clarification_passthrough",
    "clarification_confirm_switch",
    "clarification_current_topic",
    "clarification_new_topic",
    "clarification_freeform_current_topic",
    "clarification_freeform_new_topic",
    "clarification_freeform_defer",
)

_CLARIFICATION_ROUTE_TARGETS = {
    "clarification_passthrough": "clarification_passthrough",
    "clarification_confirm_switch": "clarification_confirm_switch",
    "clarification_current_topic": "clarification_current_topic",
    "clarification_new_topic": "clarification_new_topic",
    "clarification_freeform_router": "clarification_freeform_router",
}

_CLARIFICATION_FREEFORM_ROUTE_TARGETS = {
    "clarification_freeform_current_topic": "clarification_freeform_current_topic",
    "clarification_freeform_new_topic": "clarification_freeform_new_topic",
    "clarification_freeform_defer": "clarification_freeform_defer",
}


def _build_clarification_handler_targets(
    include_compose_answer: bool,
):
    targets = {
        "intent_guard": "intent_guard",
        "retrieve_context": "retrieve_context",
        "clarification_freeform_router": "clarification_freeform_router",
        "end": END,
    }
    if include_compose_answer:
        targets["compose_answer"] = "compose_answer"
    return targets


def _build_intent_guard_targets(include_compose_answer: bool):
    targets = {"retrieve_context": "retrieve_context"}
    if include_compose_answer:
        targets["compose_answer"] = "compose_answer"
    else:
        targets["end"] = END
    return targets


def _build_review_gate_targets(include_compose_answer: bool):
    targets = {"review_hold": "review_hold"}
    if include_compose_answer:
        targets["compose_answer"] = "compose_answer"
    else:
        targets["end"] = END
    return targets


def _build_review_hold_targets(include_compose_answer: bool):
    if include_compose_answer:
        return {
            "compose_answer": "compose_answer",
            "end": END,
        }
    return {"end": END}


def _register_workflow_nodes(
    builder: StateGraph,
    *,
    include_compose_answer: bool,
) -> None:
    for node_name, node_handler in _WORKFLOW_NODES:
        builder.add_node(node_name, node_handler)
    if include_compose_answer:
        builder.add_node("compose_answer", _compose_answer)


def _add_clarification_handler_edges(
    builder: StateGraph,
    *,
    include_compose_answer: bool,
) -> None:
    def route(state):
        return _route_after_clarification_handler(
            state,
            include_compose_answer=include_compose_answer,
        )

    targets = _build_clarification_handler_targets(include_compose_answer)
    for node_name in _CLARIFICATION_HANDLER_NODE_NAMES:
        builder.add_conditional_edges(node_name, route, targets)


def build_chat_workflow(
    *,
    include_compose_answer: bool,
    checkpointer=None,
):
    builder = StateGraph(ChatWorkflowState)

    def route_after_intent_guard(state):
        return _route_after_intent_guard(
            state,
            include_compose_answer=include_compose_answer,
        )

    def route_after_review_gate(state):
        return _route_after_review_gate(
            state,
            include_compose_answer=include_compose_answer,
        )

    def route_after_review_hold(state):
        return _route_after_review_hold(
            state,
            include_compose_answer=include_compose_answer,
        )

    _register_workflow_nodes(
        builder,
        include_compose_answer=include_compose_answer,
    )

    builder.add_edge(START, "assistant_config")
    builder.add_edge("assistant_config", "kb_scope")
    builder.add_edge("kb_scope", "question_intake")
    builder.add_edge("question_intake", "memory_manager")
    builder.add_edge("memory_manager", "clarification_router")
    builder.add_conditional_edges(
        "clarification_router",
        _route_after_clarification_router,
        _CLARIFICATION_ROUTE_TARGETS,
    )
    builder.add_conditional_edges(
        "clarification_freeform_router",
        _route_after_clarification_freeform_router,
        _CLARIFICATION_FREEFORM_ROUTE_TARGETS,
    )
    _add_clarification_handler_edges(
        builder,
        include_compose_answer=include_compose_answer,
    )
    builder.add_conditional_edges(
        "intent_guard",
        route_after_intent_guard,
        _build_intent_guard_targets(include_compose_answer),
    )
    builder.add_edge("retrieve_context", "review_gate")
    builder.add_conditional_edges(
        "review_gate",
        route_after_review_gate,
        _build_review_gate_targets(include_compose_answer),
    )
    builder.add_conditional_edges(
        "review_hold",
        route_after_review_hold,
        _build_review_hold_targets(include_compose_answer),
    )
    if include_compose_answer:
        builder.add_edge("compose_answer", END)
    return builder.compile(checkpointer=checkpointer)
