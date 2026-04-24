from datetime import datetime

from pydantic import BaseModel


class TaskSlaSnapshot(BaseModel):
    policy_key: str
    policy_name: str
    status: str
    target_seconds: int
    warning_seconds: int
    elapsed_seconds: int
    remaining_seconds: int
    breach_seconds: int
    deadline_at: datetime
    resolved_at: datetime | None = None
    resolution_seconds: int | None = None
    target_met: bool | None = None
