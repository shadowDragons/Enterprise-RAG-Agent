from types import SimpleNamespace

import pytest

from app.db.schema_management import (
    describe_database_schema_strategy,
    resolve_database_schema_strategy,
    run_alembic_upgrade,
)


def _build_settings(
    *,
    strategy: str = "auto",
    app_env: str = "dev",
    database_url: str = "sqlite:///./storage/test.db",
):
    return SimpleNamespace(
        database_schema_strategy=strategy,
        app_env=app_env,
        database_url=database_url,
    )


def test_schema_strategy_uses_create_all_for_dev_sqlite() -> None:
    settings = _build_settings(app_env="dev", database_url="sqlite:///./storage/dev.db")
    strategy, label = describe_database_schema_strategy(settings=settings)

    assert resolve_database_schema_strategy(settings=settings) == "create_all"
    assert strategy == "create_all"
    assert "create_all" in label


def test_schema_strategy_uses_migrate_for_prod_postgres() -> None:
    settings = _build_settings(
        app_env="prod",
        database_url="postgresql+psycopg://rag:rag@localhost:5432/enterprise_rag",
    )

    assert resolve_database_schema_strategy(settings=settings) == "migrate"


def test_schema_strategy_rejects_invalid_value() -> None:
    settings = _build_settings(strategy="broken")

    with pytest.raises(RuntimeError, match="不支持的 database_schema_strategy"):
        resolve_database_schema_strategy(settings=settings)


def test_run_alembic_upgrade_raises_clear_error_when_alembic_missing(
    monkeypatch,
) -> None:
    def _raise_missing():
        raise RuntimeError("当前环境未安装 Alembic。生产模式请执行 `pip install -e \".[prod]\"`。")

    monkeypatch.setattr(
        "app.db.schema_management._load_alembic_runtime",
        _raise_missing,
    )
    settings = _build_settings(strategy="migrate")

    with pytest.raises(RuntimeError, match="未安装 Alembic"):
        run_alembic_upgrade(settings=settings)
