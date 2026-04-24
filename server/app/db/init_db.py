from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import hash_password, verify_password
from app.core.config import get_settings
from app.core.review_rules import default_review_rules
from app.db.schema_management import ensure_database_schema
from app.db.session import SessionLocal
from app.models import Assistant, AssistantVersion, AuthUser, KnowledgeBase
from app.services.assistant_configs import build_assistant_snapshot_payload


def init_db() -> None:
    settings = get_settings()
    Path(settings.storage_root).mkdir(parents=True, exist_ok=True)
    strategy = ensure_database_schema(settings=settings)
    if strategy == "skip":
        return

    with SessionLocal() as db:
        seed_defaults(db)


def seed_defaults(db: Session) -> None:
    _seed_auth_users(db)

    kb_exists = db.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.knowledge_base_id == "kb-demo-001"
        )
    )
    if not kb_exists:
        kb_exists = KnowledgeBase(
            knowledge_base_id="kb-demo-001",
            knowledge_base_name="默认知识库",
            description="系统初始化创建的默认知识库。",
            default_retrieval_top_k=5,
        )
        db.add(kb_exists)
    else:
        kb_exists.knowledge_base_name = "默认知识库"
        kb_exists.description = "系统初始化创建的默认知识库。"
        kb_exists.default_retrieval_top_k = 5

    assistant_exists = db.scalar(
        select(Assistant).where(Assistant.assistant_id == "asst-demo-001")
    )
    if not assistant_exists:
        assistant_exists = Assistant(
            assistant_id="asst-demo-001",
            assistant_name="通用知识助手",
            description="系统初始化创建的默认助理。",
            system_prompt="你是一个默认的企业级 RAG 智能助手，请优先用中文回答用户问题。",
            default_model="gpt-4o",
            default_kb_ids=["kb-demo-001"],
            tool_keys=[],
            review_rules=default_review_rules(),
            review_enabled=False,
            version=1,
        )
        db.add(assistant_exists)
    else:
        assistant_exists.assistant_name = "通用知识助手"
        assistant_exists.description = "系统初始化创建的默认助理。"
        assistant_exists.system_prompt = (
            "你是一个默认的企业级 RAG 智能助手，请优先用中文回答用户问题。"
        )
        assistant_exists.default_model = "gpt-4o"
        assistant_exists.default_kb_ids = ["kb-demo-001"]
        assistant_exists.tool_keys = []
        assistant_exists.review_rules = default_review_rules()
        assistant_exists.review_enabled = False
        assistant_exists.version = 1

    version_exists = db.scalar(
        select(AssistantVersion).where(
            AssistantVersion.assistant_id == assistant_exists.assistant_id,
            AssistantVersion.version == assistant_exists.version,
        )
    )
    if not version_exists:
        db.add(
            AssistantVersion(
                assistant_version_id=str(uuid4()),
                assistant_id=assistant_exists.assistant_id,
                version=assistant_exists.version,
                change_note="系统初始化",
                snapshot_payload=build_assistant_snapshot_payload(assistant_exists),
            )
        )

    db.commit()


def _seed_auth_users(db: Session) -> None:
    for spec in (
        {
            "user_id": "user-admin-001",
            "username": "admin",
            "display_name": "系统管理员",
            "password": "admin123456",
            "roles": ["admin"],
        },
        {
            "user_id": "user-operator-001",
            "username": "operator",
            "display_name": "运营人员",
            "password": "operator123456",
            "roles": ["operator"],
        },
        {
            "user_id": "user-viewer-001",
            "username": "viewer",
            "display_name": "访客用户",
            "password": "viewer123456",
            "roles": ["viewer"],
        },
    ):
        user = db.scalar(select(AuthUser).where(AuthUser.username == spec["username"]))
        if not user:
            user = AuthUser(
                user_id=spec["user_id"],
                username=spec["username"],
                display_name=spec["display_name"],
                password_hash=hash_password(spec["password"]),
                roles=list(spec["roles"]),
                is_active=True,
            )
            db.add(user)
            continue

        user.display_name = spec["display_name"]
        user.roles = list(spec["roles"])
        user.is_active = True
        if not verify_password(spec["password"], user.password_hash):
            user.password_hash = hash_password(spec["password"])
