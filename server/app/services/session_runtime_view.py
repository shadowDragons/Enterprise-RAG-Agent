from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.integrations.langgraph_checkpointer import (
    decode_database_checkpoint_value,
    describe_workflow_checkpointer_backend,
)
from app.models import ReviewTask, WorkflowCheckpoint
from app.schemas.session import SessionWorkflowRuntime
from app.services.review_tasks import ReviewTaskService


@dataclass
class WorkflowCheckpointRuntimeSnapshot:
    checkpoint: WorkflowCheckpoint
    metadata: dict
    pending_write_count: int


def _pending_review_map(
    db: Session,
    session_ids: set[str] | None = None,
) -> dict[str, ReviewTask]:
    stmt = (
        db.query(ReviewTask)
        .filter(ReviewTask.status.in_(("pending", "escalated")))
        .order_by(ReviewTask.created_at.desc())
    )
    if session_ids:
        stmt = stmt.filter(ReviewTask.session_id.in_(session_ids))

    result: dict[str, ReviewTask] = {}
    for review_task in stmt.all():
        result.setdefault(review_task.session_id, review_task)
    return result


def _decode_checkpoint_metadata(payload: dict) -> dict:
    if not isinstance(payload, dict) or not payload:
        return {}

    decoded = decode_database_checkpoint_value(payload)
    return decoded if isinstance(decoded, dict) else {}


def _checkpoint_runtime_map(
    db: Session,
    thread_ids: set[str],
) -> dict[str, WorkflowCheckpointRuntimeSnapshot]:
    if not thread_ids:
        return {}

    checkpoints = (
        db.query(WorkflowCheckpoint)
        .filter(WorkflowCheckpoint.thread_id.in_(thread_ids))
        .order_by(
            WorkflowCheckpoint.thread_id.asc(),
            WorkflowCheckpoint.checkpoint_id.desc(),
        )
        .all()
    )
    result: dict[str, WorkflowCheckpointRuntimeSnapshot] = {}
    for checkpoint in checkpoints:
        existing = result.get(checkpoint.thread_id)
        if existing is None:
            result[checkpoint.thread_id] = WorkflowCheckpointRuntimeSnapshot(
                checkpoint=checkpoint,
                metadata=_decode_checkpoint_metadata(checkpoint.metadata_payload),
                pending_write_count=len(checkpoint.pending_writes_payload),
            )
            continue

        existing.pending_write_count += len(checkpoint.pending_writes_payload)
    return result


def _coerce_runtime_context(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict) or not payload:
        return None
    return dict(payload)


def _normalize_runtime_text(value) -> str | None:
    text = str(value or "").strip()
    return text or None


def _resolve_lifecycle_runtime(
    *,
    session,
    session_status: str,
    runtime_context: dict | None,
    review_task: ReviewTask | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    runtime_state = _normalize_runtime_text(getattr(session, "runtime_state", ""))
    runtime_label = _normalize_runtime_text(getattr(session, "runtime_label", ""))
    runtime_waiting_for = _normalize_runtime_text(
        getattr(session, "runtime_waiting_for", "")
    )
    runtime_resume_strategy = _normalize_runtime_text(
        getattr(session, "runtime_resume_strategy", "")
    )
    if runtime_state and runtime_state != "idle":
        return (
            runtime_state,
            runtime_label,
            runtime_waiting_for,
            runtime_resume_strategy or "none",
        )

    clarification_stage = _normalize_runtime_text(
        getattr(session, "runtime_clarification_stage", "")
    ) or _normalize_runtime_text((runtime_context or {}).get("clarification_stage"))
    if review_task is not None or session_status == "awaiting_review":
        if review_task is not None and review_task.status == "escalated":
            return (
                "waiting_review_escalated",
                "人工审核已超时，等待升级处理",
                "escalated_human_review",
                "command_resume",
            )
        return (
            "waiting_review",
            "等待人工审核",
            "human_review",
            "command_resume",
        )
    if session_status == "awaiting_clarification":
        if clarification_stage == "collect_new_topic_question":
            return (
                "waiting_new_topic_question",
                "等待输入新主题问题",
                "new_topic_question",
                "new_user_message",
            )
        if clarification_stage == "collect_current_topic_question":
            return (
                "waiting_clarification_question",
                "等待补充具体问题",
                "follow_up_question",
                "new_user_message",
            )
        return (
            "waiting_clarification_switch",
            "等待确认是否切换主题",
            "topic_switch_confirmation",
            "new_user_message",
        )
    return "completed", "本轮已完成", None, "none"


def _resolve_formal_runtime_fields(session) -> dict[str, str | None]:
    return {
        "current_goal": _normalize_runtime_text(
            getattr(session, "runtime_current_goal", "")
        ),
        "resolved_question": _normalize_runtime_text(
            getattr(session, "runtime_resolved_question", "")
        ),
        "pending_question": _normalize_runtime_text(
            getattr(session, "runtime_pending_question", "")
        ),
        "clarification_type": _normalize_runtime_text(
            getattr(session, "runtime_clarification_type", "")
        ),
        "clarification_stage": _normalize_runtime_text(
            getattr(session, "runtime_clarification_stage", "")
        ),
        "clarification_expected_input": _normalize_runtime_text(
            getattr(session, "runtime_clarification_expected_input", "")
        ),
        "clarification_reason": _normalize_runtime_text(
            getattr(session, "runtime_clarification_reason", "")
        ),
    }


def _resolve_checkpoint_runtime(
    *,
    workflow_thread_id: str | None,
    checkpoint: WorkflowCheckpoint | None,
    workflow_can_resume: bool,
    pending_write_count: int | None,
    checkpoint_backend: str,
) -> tuple[str | None, str | None]:
    if checkpoint_backend != "database":
        if workflow_thread_id is not None and workflow_can_resume:
            return "external_resumable", "由外部 checkpointer 管理，可继续恢复"
        if workflow_thread_id is not None:
            return "external_managed", "由外部 checkpointer 管理"
        return None, None

    if checkpoint is not None and workflow_can_resume:
        return "resumable", "存在可恢复 checkpoint"
    if checkpoint is not None and (pending_write_count or 0) > 0:
        return "pending_writes", "checkpoint 已落盘，仍有待清理写入"
    if checkpoint is not None:
        return "settled", "checkpoint 已落盘"
    if workflow_thread_id is not None:
        return "thread_bound", "已记录 workflow thread"
    return None, None


def _latest_trace_snapshot(
    *,
    runtime_context: dict | None,
    review_task: ReviewTask | None,
) -> tuple[str | None, str | None]:
    if runtime_context:
        latest_node = str(runtime_context.get("latest_trace_node", "")).strip() or None
        latest_detail = (
            str(runtime_context.get("latest_trace_detail", "")).strip() or None
        )
        if latest_node or latest_detail:
            return latest_node, latest_detail

    if review_task and review_task.workflow_trace:
        last_item = review_task.workflow_trace[-1]
        if isinstance(last_item, dict):
            latest_node = str(last_item.get("node", "")).strip() or None
            latest_detail = str(last_item.get("detail", "")).strip() or None
            return latest_node, latest_detail

    return None, None


def build_session_runtime_map(
    db: Session,
    sessions: list,
) -> dict[str, SessionWorkflowRuntime]:
    ReviewTaskService(db).reconcile_overdue_reviews()
    session_ids = {item.session_id for item in sessions}
    pending_reviews = _pending_review_map(db, session_ids)
    checkpoint_backend, checkpoint_backend_label = (
        describe_workflow_checkpointer_backend()
    )
    thread_ids = {
        item.workflow_thread_id.strip()
        for item in sessions
        if item.workflow_thread_id.strip()
    }
    thread_ids.update(
        str((review_task.checkpoint_payload or {}).get("workflow_thread_id", "")).strip()
        for review_task in pending_reviews.values()
        if str((review_task.checkpoint_payload or {}).get("workflow_thread_id", "")).strip()
    )
    checkpoint_map = (
        _checkpoint_runtime_map(db, thread_ids)
        if checkpoint_backend == "database"
        else {}
    )

    runtime_map: dict[str, SessionWorkflowRuntime] = {}
    for session in sessions:
        review_task = pending_reviews.get(session.session_id)
        formal_runtime = _resolve_formal_runtime_fields(session)
        payload = review_task.checkpoint_payload if review_task is not None else {}
        workflow_thread_id = session.workflow_thread_id.strip() or str(
            payload.get("workflow_thread_id", "")
        ).strip()
        workflow_thread_id = workflow_thread_id or None
        checkpoint_runtime = (
            checkpoint_map.get(workflow_thread_id)
            if workflow_thread_id is not None
            else None
        )
        checkpoint = checkpoint_runtime.checkpoint if checkpoint_runtime else None
        runtime_reason = None
        if review_task is not None:
            if review_task.status == "escalated":
                runtime_reason = (
                    review_task.escalation_reason.strip()
                    or session.runtime_reason.strip()
                    or None
                )
            else:
                runtime_reason = (
                    review_task.review_reason.strip()
                    or session.runtime_reason.strip()
                    or None
                )
        else:
            runtime_reason = session.runtime_reason.strip() or None
        runtime_context = _coerce_runtime_context(session.runtime_context)
        latest_node, latest_node_detail = _latest_trace_snapshot(
            runtime_context=runtime_context,
            review_task=review_task,
        )
        workflow_metadata = checkpoint_runtime.metadata if checkpoint_runtime else {}
        workflow_source = str(workflow_metadata.get("source", "")).strip() or None
        workflow_step = workflow_metadata.get("step")
        if not isinstance(workflow_step, int):
            workflow_step = None
        pending_write_count = (
            checkpoint_runtime.pending_write_count if checkpoint_runtime else None
        )
        if review_task is None and session.status != "awaiting_review":
            pending_write_count = 0 if checkpoint_runtime is not None else None
        workflow_can_resume = review_task is not None or session.status == "awaiting_review"
        runtime_state, runtime_label, waiting_for, resume_strategy = (
            _resolve_lifecycle_runtime(
                session=session,
                session_status=session.status,
                runtime_context=runtime_context,
                review_task=review_task,
            )
        )
        checkpoint_status, checkpoint_label = _resolve_checkpoint_runtime(
            workflow_thread_id=workflow_thread_id,
            checkpoint=checkpoint,
            workflow_can_resume=workflow_can_resume,
            pending_write_count=pending_write_count,
            checkpoint_backend=checkpoint_backend,
        )
        if not any(
            (
                review_task is not None,
                workflow_thread_id is not None,
                checkpoint is not None,
                runtime_reason,
                runtime_context,
                formal_runtime["current_goal"],
                formal_runtime["resolved_question"],
                formal_runtime["pending_question"],
                formal_runtime["clarification_stage"],
                latest_node,
            )
        ):
            continue

        runtime_map[session.session_id] = SessionWorkflowRuntime(
            runtime_schema_version=(
                int(runtime_context.get("runtime_schema_version"))
                if isinstance(runtime_context, dict)
                and isinstance(runtime_context.get("runtime_schema_version"), int)
                else None
            ),
            runtime_state=runtime_state,
            runtime_label=runtime_label,
            current_goal=formal_runtime["current_goal"],
            resolved_question=formal_runtime["resolved_question"],
            pending_question=formal_runtime["pending_question"],
            clarification_type=formal_runtime["clarification_type"],
            clarification_stage=formal_runtime["clarification_stage"],
            clarification_expected_input=formal_runtime[
                "clarification_expected_input"
            ],
            clarification_reason=formal_runtime["clarification_reason"],
            pending_review_id=review_task.review_id if review_task else None,
            pending_review_reason=(
                review_task.review_reason.strip() or None if review_task else None
            ),
            pending_review_status=(
                review_task.status.strip() or None if review_task else None
            ),
            pending_review_escalation_reason=(
                review_task.escalation_reason.strip() or None if review_task else None
            ),
            pending_review_escalated_at=(
                review_task.escalated_at if review_task else None
            ),
            runtime_reason=runtime_reason,
            waiting_for=waiting_for,
            resume_strategy=resume_strategy,
            latest_node=latest_node,
            latest_node_detail=latest_node_detail,
            workflow_thread_id=workflow_thread_id,
            workflow_checkpoint_id=(
                checkpoint.checkpoint_id if checkpoint is not None else None
            ),
            workflow_checkpoint_updated_at=(
                checkpoint.updated_at if checkpoint is not None else None
            ),
            workflow_source=workflow_source,
            workflow_step=workflow_step,
            workflow_checkpoint_backend=checkpoint_backend,
            workflow_checkpoint_backend_label=checkpoint_backend_label,
            checkpoint_status=checkpoint_status,
            checkpoint_label=checkpoint_label,
            workflow_pending_write_count=pending_write_count,
            workflow_can_resume=workflow_can_resume,
        )
    return runtime_map
