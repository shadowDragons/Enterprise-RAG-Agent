"""baseline latest schema

Revision ID: 20260420_0001
Revises: None
Create Date: 2026-04-20 00:00:00
"""

from alembic import op

from app.db.base import Base
from app.models import (  # noqa: F401
    Assistant,
    AssistantVersion,
    AuditLog,
    AuthUser,
    Document,
    DocumentChunk,
    Job,
    KnowledgeBase,
    Message,
    ReviewTask,
    Session,
    WorkflowCheckpoint,
)

# revision identifiers, used by Alembic.
revision = "20260420_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
