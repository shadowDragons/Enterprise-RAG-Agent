from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.models import Job


class JobRepository:
    def __init__(self, db: DBSession):
        self.db = db

    def list(
        self,
        job_type: str | None = None,
        status: str | None = None,
    ) -> list[Job]:
        stmt = select(Job).order_by(Job.created_at.desc())
        if job_type:
            stmt = stmt.where(Job.job_type == job_type)
        if status:
            stmt = stmt.where(Job.status == status)
        return list(self.db.scalars(stmt).all())

    def get(self, job_id: str) -> Job | None:
        stmt = select(Job).where(Job.job_id == job_id)
        return self.db.scalar(stmt)
