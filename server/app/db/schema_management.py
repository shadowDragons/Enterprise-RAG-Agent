from importlib import import_module
from pathlib import Path

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine


_CREATE_ALL_STRATEGY = "create_all"
_MIGRATE_STRATEGY = "migrate"
_SKIP_STRATEGY = "skip"


def resolve_database_schema_strategy(*, settings=None) -> str:
    resolved_settings = settings or get_settings()
    configured_strategy = str(
        resolved_settings.database_schema_strategy or "auto"
    ).strip().lower()
    database_url = str(resolved_settings.database_url or "").strip().lower()
    app_env = str(resolved_settings.app_env or "dev").strip().lower()

    if configured_strategy in {"", "auto"}:
        if app_env in {"dev", "test"} and database_url.startswith("sqlite"):
            return _CREATE_ALL_STRATEGY
        return _MIGRATE_STRATEGY

    if configured_strategy in {
        _CREATE_ALL_STRATEGY,
        _MIGRATE_STRATEGY,
        _SKIP_STRATEGY,
    }:
        return configured_strategy

    raise RuntimeError(f"不支持的 database_schema_strategy：{configured_strategy}")


def describe_database_schema_strategy(*, settings=None) -> tuple[str, str]:
    strategy = resolve_database_schema_strategy(settings=settings)
    if strategy == _CREATE_ALL_STRATEGY:
        return strategy, "使用 SQLAlchemy create_all 初始化数据库"
    if strategy == _MIGRATE_STRATEGY:
        return strategy, "使用 Alembic migration 升级到最新 schema"
    return strategy, "跳过数据库 schema 初始化"


def ensure_database_schema(*, settings=None) -> str:
    strategy = resolve_database_schema_strategy(settings=settings)
    if strategy == _SKIP_STRATEGY:
        return strategy
    if strategy == _CREATE_ALL_STRATEGY:
        Base.metadata.create_all(bind=engine)
        return strategy

    run_alembic_upgrade("head", settings=settings)
    return strategy


def run_alembic_upgrade(revision: str = "head", *, settings=None) -> None:
    alembic_command, alembic_config = _load_alembic_runtime()
    resolved_settings = settings or get_settings()
    server_root = Path(__file__).resolve().parents[2]
    config = alembic_config.Config(str(server_root / "alembic.ini"))
    config.set_main_option("script_location", str(server_root / "alembic"))
    config.set_main_option("sqlalchemy.url", str(resolved_settings.database_url))
    alembic_command.upgrade(config, revision)


def _load_alembic_runtime():
    try:
        alembic_command = import_module("alembic.command")
        alembic_config = import_module("alembic.config")
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError(
            "当前环境未安装 Alembic。生产模式请执行 `pip install -e \".[prod]\"`。"
        ) from exc
    return alembic_command, alembic_config
