from __future__ import annotations

import json
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.core.config import get_settings
from app.integrations.langgraph_checkpointer import (
    create_workflow_checkpointer,
    describe_workflow_checkpointer_backend,
)


class ProbeState(TypedDict, total=False):
    question: str
    approved: bool


def _pause_for_resume(state: ProbeState) -> ProbeState:
    payload = interrupt(
        {
            "type": "postgres_checkpointer_probe",
            "question": state.get("question", "probe"),
        }
    )
    if not isinstance(payload, dict):
        payload = {}
    return {"approved": bool(payload.get("approved", False))}


def _build_probe_workflow(checkpointer):
    builder = StateGraph(ProbeState)
    builder.add_node("pause_for_resume", _pause_for_resume)
    builder.add_edge(START, "pause_for_resume")
    builder.add_edge("pause_for_resume", END)
    return builder.compile(checkpointer=checkpointer)


def main() -> int:
    settings = get_settings()
    backend, backend_label = describe_workflow_checkpointer_backend(settings=settings)
    if backend != "postgres":
        raise SystemExit(
            "当前 workflow checkpointer backend 不是 postgres，"
            "请先设置 WORKFLOW_CHECKPOINTER_BACKEND=postgres。"
        )

    checkpointer = create_workflow_checkpointer(settings=settings)
    workflow = _build_probe_workflow(checkpointer)
    thread_id = f"postgres-checkpointer-probe-{uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}

    interrupted = workflow.invoke({"question": "probe"}, config=config)
    if not interrupted.get("__interrupt__"):
        raise SystemExit("探针流程未产生 interrupt，无法验证 official saver 的恢复能力。")

    resumed = workflow.invoke(Command(resume={"approved": True}), config=config)
    if resumed.get("approved") is not True:
        raise SystemExit("探针流程恢复后未拿到预期结果，official saver 验证失败。")

    print(
        json.dumps(
            {
                "status": "ok",
                "backend": backend,
                "backend_label": backend_label,
                "thread_id": thread_id,
                "resume_verified": True,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
