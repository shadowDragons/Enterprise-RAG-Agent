from types import SimpleNamespace

import pytest

from app.integrations.langgraph_checkpointer import (
    DatabaseCheckpointSaver,
    create_workflow_checkpointer,
    describe_workflow_checkpointer_backend,
    resolve_workflow_checkpointer_backend,
)


def _build_settings(
    *,
    backend: str = "auto",
    postgres_url: str = "",
    database_url: str = "sqlite:///./storage/test.db",
):
    return SimpleNamespace(
        workflow_checkpointer_backend=backend,
        workflow_checkpointer_postgres_url=postgres_url,
        database_url=database_url,
    )


def test_checkpointer_factory_falls_back_to_database_when_postgres_saver_missing(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.integrations.langgraph_checkpointer._load_official_postgres_saver_class",
        lambda: None,
    )
    settings = _build_settings(
        backend="auto",
        postgres_url="postgresql://demo:demo@localhost:5432/rag",
    )

    saver = create_workflow_checkpointer(settings=settings)
    backend, label = describe_workflow_checkpointer_backend(settings=settings)

    assert isinstance(saver, DatabaseCheckpointSaver)
    assert resolve_workflow_checkpointer_backend(settings=settings) == "database"
    assert backend == "database"
    assert "内置数据库" in label


def test_checkpointer_factory_uses_official_postgres_saver_when_available(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeSaver:
        def setup(self):
            captured["setup_called"] = True

    class FakeContext:
        def __enter__(self):
            return FakeSaver()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakePostgresSaver:
        @classmethod
        def from_conn_string(cls, conn_string: str):
            captured["conn_string"] = conn_string
            return FakeContext()

    monkeypatch.setattr(
        "app.integrations.langgraph_checkpointer._load_official_postgres_saver_class",
        lambda: FakePostgresSaver,
    )
    settings = _build_settings(
        backend="postgres",
        postgres_url="postgresql://demo:demo@localhost:5432/rag",
    )

    saver = create_workflow_checkpointer(settings=settings)
    backend, label = describe_workflow_checkpointer_backend(settings=settings)

    assert captured["conn_string"] == settings.workflow_checkpointer_postgres_url
    assert captured["setup_called"] is True
    assert isinstance(saver, FakeSaver)
    assert hasattr(saver, "_managed_checkpoint_context")
    assert backend == "postgres"
    assert "Postgres" in label


def test_checkpointer_factory_raises_when_postgres_setup_fails(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {"closed": False}

    class FakeSaver:
        def setup(self):
            raise RuntimeError("boom")

    class FakeContext:
        def __enter__(self):
            return FakeSaver()

        def __exit__(self, exc_type, exc, tb):
            captured["closed"] = True
            return False

    class FakePostgresSaver:
        @classmethod
        def from_conn_string(cls, conn_string: str):
            return FakeContext()

    monkeypatch.setattr(
        "app.integrations.langgraph_checkpointer._load_official_postgres_saver_class",
        lambda: FakePostgresSaver,
    )
    settings = _build_settings(
        backend="postgres",
        postgres_url="postgresql://demo:demo@localhost:5432/rag",
    )

    with pytest.raises(RuntimeError, match="初始化失败"):
        create_workflow_checkpointer(settings=settings)

    assert captured["closed"] is True


def test_checkpointer_factory_raises_when_postgres_is_explicit_but_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.integrations.langgraph_checkpointer._load_official_postgres_saver_class",
        lambda: None,
    )
    settings = _build_settings(
        backend="postgres",
        postgres_url="postgresql://demo:demo@localhost:5432/rag",
    )

    with pytest.raises(RuntimeError, match="未安装官方 Postgres checkpointer"):
        create_workflow_checkpointer(settings=settings)


def test_checkpointer_factory_treats_sqlalchemy_psycopg_url_as_postgres(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.integrations.langgraph_checkpointer._load_official_postgres_saver_class",
        lambda: None,
    )
    settings = _build_settings(
        backend="auto",
        postgres_url="",
        database_url="postgresql+psycopg://rag:rag@localhost:5432/enterprise_rag",
    )

    assert resolve_workflow_checkpointer_backend(settings=settings) == "database"
