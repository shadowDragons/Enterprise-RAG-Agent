from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.models import Job, ReviewTask


@dataclass(frozen=True)
class TaskSlaPolicy:
    key: str
    label: str
    target_seconds: int
    warning_ratio: float = 0.7

    @property
    def warning_seconds(self) -> int:
        return max(1, int(self.target_seconds * self.warning_ratio))


DOCUMENT_INGESTION_SLA = TaskSlaPolicy(
    key="document_ingestion",
    label="文档入库",
    target_seconds=300,
    warning_ratio=0.6,
)

HUMAN_REVIEW_SLA = TaskSlaPolicy(
    key="human_review",
    label="人工审核",
    target_seconds=1800,
    warning_ratio=0.5,
)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _seconds_between(later: datetime, earlier: datetime) -> int:
    return max(0, int((later - earlier).total_seconds()))


def build_task_sla_snapshot(
    *,
    created_at: datetime,
    updated_at: datetime,
    current_status: str,
    policy: TaskSlaPolicy,
    completed_statuses: set[str],
    failed_statuses: set[str],
    resolved_at: datetime | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    created_at_utc = _to_utc(created_at)
    updated_at_utc = _to_utc(updated_at)
    current_time = _to_utc(now or datetime.now(timezone.utc))
    deadline_at = created_at_utc + timedelta(seconds=policy.target_seconds)
    elapsed_seconds = _seconds_between(current_time, created_at_utc)
    remaining_seconds = policy.target_seconds - elapsed_seconds
    breach_seconds = max(0, elapsed_seconds - policy.target_seconds)

    snapshot_status = "normal"
    resolved_at_utc: datetime | None = None
    resolution_seconds: int | None = None
    target_met: bool | None = None

    if current_status in failed_statuses:
        snapshot_status = "failed"
    elif current_status in completed_statuses:
        snapshot_status = "completed"
    elif elapsed_seconds >= policy.target_seconds:
        snapshot_status = "breached"
    elif elapsed_seconds >= policy.warning_seconds:
        snapshot_status = "warning"

    if snapshot_status in {"completed", "failed"}:
        resolved_at_utc = _to_utc(resolved_at or updated_at_utc)
        resolution_seconds = _seconds_between(resolved_at_utc, created_at_utc)
        target_met = resolution_seconds <= policy.target_seconds
        remaining_seconds = policy.target_seconds - resolution_seconds
        breach_seconds = max(0, resolution_seconds - policy.target_seconds)

    return {
        "policy_key": policy.key,
        "policy_name": policy.label,
        "status": snapshot_status,
        "target_seconds": policy.target_seconds,
        "warning_seconds": policy.warning_seconds,
        "elapsed_seconds": elapsed_seconds,
        "remaining_seconds": remaining_seconds,
        "breach_seconds": breach_seconds,
        "deadline_at": deadline_at,
        "resolved_at": resolved_at_utc,
        "resolution_seconds": resolution_seconds,
        "target_met": target_met,
    }


def build_job_sla_snapshot(job: Job) -> dict[str, object]:
    policy = DOCUMENT_INGESTION_SLA
    return build_task_sla_snapshot(
        created_at=job.created_at,
        updated_at=job.updated_at,
        current_status=job.status,
        policy=policy,
        completed_statuses={"completed"},
        failed_statuses={"failed"},
    )


def build_review_sla_snapshot(review_task: ReviewTask) -> dict[str, object]:
    policy = HUMAN_REVIEW_SLA
    return build_task_sla_snapshot(
        created_at=review_task.created_at,
        updated_at=review_task.updated_at,
        current_status=review_task.status,
        policy=policy,
        completed_statuses={"approved", "rejected"},
        failed_statuses=set(),
        resolved_at=review_task.reviewed_at,
    )
