import base64
import copy
import importlib
from collections.abc import Iterator, Sequence
from functools import lru_cache
from typing import Any

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)
from langgraph.checkpoint.memory import WRITES_IDX_MAP

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.repositories.workflow_checkpoints import WorkflowCheckpointRepository

_DATABASE_CHECKPOINTER_BACKEND = "database"
_POSTGRES_CHECKPOINTER_BACKEND = "postgres"


def _is_postgres_url(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized.startswith("postgres")


def _resolve_postgres_checkpointer_url(settings=None) -> str:
    resolved_settings = settings or get_settings()
    configured_url = str(
        resolved_settings.workflow_checkpointer_postgres_url or ""
    ).strip()
    if configured_url:
        return configured_url

    database_url = str(resolved_settings.database_url or "").strip()
    if _is_postgres_url(database_url):
        return database_url
    return ""


def _load_official_postgres_saver_class():
    candidates = (
        ("langgraph.checkpoint.postgres", "PostgresSaver"),
        ("langgraph_checkpoint_postgres", "PostgresSaver"),
    )
    for module_name, attr_name in candidates:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        saver_class = getattr(module, attr_name, None)
        if saver_class is not None:
            return saver_class
    return None


def resolve_workflow_checkpointer_backend(*, settings=None) -> str:
    resolved_settings = settings or get_settings()
    configured_backend = str(
        resolved_settings.workflow_checkpointer_backend or "auto"
    ).strip().lower()
    postgres_url = _resolve_postgres_checkpointer_url(resolved_settings)
    postgres_saver_class = _load_official_postgres_saver_class()

    if configured_backend in {"", "auto"}:
        if postgres_url and postgres_saver_class is not None:
            return _POSTGRES_CHECKPOINTER_BACKEND
        return _DATABASE_CHECKPOINTER_BACKEND

    if configured_backend in {"db", "database"}:
        return _DATABASE_CHECKPOINTER_BACKEND

    if configured_backend == _POSTGRES_CHECKPOINTER_BACKEND:
        if not postgres_url:
            raise RuntimeError(
                "workflow_checkpointer_backend=postgres，但未配置可用的 Postgres 连接串。"
            )
        if postgres_saver_class is None:
            raise RuntimeError(
                "workflow_checkpointer_backend=postgres，但当前环境未安装官方 Postgres checkpointer 依赖。"
            )
        return _POSTGRES_CHECKPOINTER_BACKEND

    raise RuntimeError(f"不支持的 workflow checkpointer backend：{configured_backend}")


def describe_workflow_checkpointer_backend(*, settings=None) -> tuple[str, str]:
    backend = resolve_workflow_checkpointer_backend(settings=settings)
    if backend == _POSTGRES_CHECKPOINTER_BACKEND:
        return backend, "官方 Postgres checkpointer"
    return backend, "内置数据库 checkpointer"


def _instantiate_official_postgres_saver(*, settings=None):
    resolved_settings = settings or get_settings()
    postgres_url = _resolve_postgres_checkpointer_url(resolved_settings)
    saver_class = _load_official_postgres_saver_class()
    if saver_class is None or not postgres_url:
        return None

    factory = getattr(saver_class, "from_conn_string", None)
    if callable(factory):
        saver_or_context = factory(postgres_url)
    else:
        saver_or_context = saver_class(postgres_url)

    if hasattr(saver_or_context, "__enter__") and hasattr(saver_or_context, "__exit__"):
        managed_context = saver_or_context
        saver = managed_context.__enter__()
        setattr(saver, "_managed_checkpoint_context", managed_context)
        return saver
    return saver_or_context


def _close_managed_checkpoint_context(saver) -> None:
    managed_context = getattr(saver, "_managed_checkpoint_context", None)
    if managed_context is None:
        return
    try:
        managed_context.__exit__(None, None, None)
    except Exception:
        return


def _initialize_official_postgres_saver(saver) -> None:
    setup = getattr(saver, "setup", None)
    if not callable(setup):
        return
    try:
        setup()
    except Exception as exc:
        _close_managed_checkpoint_context(saver)
        raise RuntimeError(
            "官方 Postgres checkpointer 初始化失败，请确认连接串、数据库可达性和账号权限。"
        ) from exc


def create_workflow_checkpointer(*, settings=None, session_factory=SessionLocal):
    backend = resolve_workflow_checkpointer_backend(settings=settings)
    if backend == _POSTGRES_CHECKPOINTER_BACKEND:
        saver = _instantiate_official_postgres_saver(settings=settings)
        if saver is None:
            raise RuntimeError("无法初始化官方 Postgres checkpointer。")
        _initialize_official_postgres_saver(saver)
        return saver
    return DatabaseCheckpointSaver(session_factory=session_factory)


@lru_cache
def get_workflow_checkpointer():
    return create_workflow_checkpointer()


@lru_cache
def _database_checkpoint_codec() -> "DatabaseCheckpointSaver":
    return DatabaseCheckpointSaver()


def decode_database_checkpoint_value(payload: dict) -> Any:
    if not isinstance(payload, dict) or not payload:
        return {}
    try:
        return _database_checkpoint_codec().decode_typed_value(payload)
    except Exception:
        return {}


class DatabaseCheckpointSaver(BaseCheckpointSaver[str]):
    """基于业务数据库持久化 LangGraph checkpoint。

    当前项目尚未安装官方 sqlite / postgres saver，这里先用一层轻量封装把
    `thread_id -> checkpoint -> pending writes` 存回业务库，保证：
    - `interrupt()` 后的状态可以跨请求恢复
    - `/reviews/{id}/approve|reject` 可以通过 `Command(resume=...)` 继续执行
    - 运行轨迹具备最小可追踪能力
    """

    def __init__(self, session_factory=SessionLocal) -> None:
        super().__init__()
        self.serde = self.with_allowlist(
            [
                ("app.schemas.chat", "ChatCitation"),
                ("app.schemas.chat", "WorkflowTraceStep"),
            ]
        ).serde
        self.session_factory = session_factory

    def get_tuple(self, config) -> CheckpointTuple | None:
        configurable = config.get("configurable", {})
        thread_id = configurable["thread_id"]
        checkpoint_ns = configurable.get("checkpoint_ns", "")
        checkpoint_id = get_checkpoint_id(config)
        with self.session_factory() as db:
            record = WorkflowCheckpointRepository(db).get(
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=checkpoint_id,
            )
        if record is None:
            return None

        checkpoint = self._decode_typed(record.checkpoint_payload)
        metadata = self._decode_typed(record.metadata_payload)
        pending_writes = [
            (
                item["task_id"],
                item["channel"],
                self._decode_typed(item["value"]),
            )
            for item in record.pending_writes_payload
        ]
        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": record.thread_id,
                    "checkpoint_ns": record.checkpoint_ns,
                    "checkpoint_id": record.checkpoint_id,
                }
            },
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=(
                {
                    "configurable": {
                        "thread_id": record.thread_id,
                        "checkpoint_ns": record.checkpoint_ns,
                        "checkpoint_id": record.parent_checkpoint_id,
                    }
                }
                if record.parent_checkpoint_id
                else None
            ),
            pending_writes=pending_writes,
        )

    def list(
        self,
        config,
        *,
        filter: dict[str, Any] | None = None,
        before=None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        thread_id = None
        checkpoint_ns = None
        if config is not None:
            configurable = config.get("configurable", {})
            thread_id = configurable.get("thread_id")
            checkpoint_ns = configurable.get("checkpoint_ns")

        before_checkpoint_id = get_checkpoint_id(before) if before else None
        with self.session_factory() as db:
            records = WorkflowCheckpointRepository(db).list(
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                before_checkpoint_id=before_checkpoint_id,
                limit=limit,
            )
        for record in records:
            metadata = self._decode_typed(record.metadata_payload)
            if filter and not all(
                metadata.get(key) == value for key, value in filter.items()
            ):
                continue
            yield CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": record.thread_id,
                        "checkpoint_ns": record.checkpoint_ns,
                        "checkpoint_id": record.checkpoint_id,
                    }
                },
                checkpoint=self._decode_typed(record.checkpoint_payload),
                metadata=metadata,
                parent_config=(
                    {
                        "configurable": {
                            "thread_id": record.thread_id,
                            "checkpoint_ns": record.checkpoint_ns,
                            "checkpoint_id": record.parent_checkpoint_id,
                        }
                    }
                    if record.parent_checkpoint_id
                    else None
                ),
                pending_writes=[
                    (
                        item["task_id"],
                        item["channel"],
                        self._decode_typed(item["value"]),
                    )
                    for item in record.pending_writes_payload
                ],
            )

    def put(
        self,
        config,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions,
    ):
        del new_versions
        configurable = config["configurable"]
        thread_id = configurable["thread_id"]
        checkpoint_ns = configurable.get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        with self.session_factory() as db:
            WorkflowCheckpointRepository(db).save(
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=checkpoint_id,
                parent_checkpoint_id=configurable.get("checkpoint_id"),
                checkpoint_payload=self._encode_typed(checkpoint),
                metadata_payload=self._encode_typed(
                    get_checkpoint_metadata(config, metadata)
                ),
            )
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        configurable = config["configurable"]
        thread_id = configurable["thread_id"]
        checkpoint_ns = configurable.get("checkpoint_ns", "")
        checkpoint_id = configurable["checkpoint_id"]
        with self.session_factory() as db:
            repository = WorkflowCheckpointRepository(db)
            record = repository.get(
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=checkpoint_id,
            )
            if record is None:
                return

            pending_writes = list(record.pending_writes_payload)
            dedupe_map = {
                (item["task_id"], item["index"]): item for item in pending_writes
            }
            for idx, (channel, value) in enumerate(writes):
                write_index = WRITES_IDX_MAP.get(channel, idx)
                key = (task_id, write_index)
                if write_index >= 0 and key in dedupe_map:
                    continue
                encoded = {
                    "task_id": task_id,
                    "channel": channel,
                    "task_path": task_path,
                    "index": write_index,
                    "value": self._encode_typed(value),
                }
                dedupe_map[key] = encoded

            sorted_writes = sorted(
                dedupe_map.values(),
                key=lambda item: (item["task_id"], item["index"], item["channel"]),
            )
            repository.update_pending_writes(
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=checkpoint_id,
                pending_writes_payload=sorted_writes,
            )

    def delete_thread(self, thread_id: str) -> None:
        with self.session_factory() as db:
            WorkflowCheckpointRepository(db).delete_thread(thread_id=thread_id)

    def delete_for_runs(self, run_ids: Sequence[str]) -> None:
        del run_ids

    def copy_thread(self, source_thread_id: str, target_thread_id: str) -> None:
        with self.session_factory() as db:
            source_records = WorkflowCheckpointRepository(db).list(
                thread_id=source_thread_id
            )
        for record in reversed(source_records):
            with self.session_factory() as db:
                repository = WorkflowCheckpointRepository(db)
                repository.save(
                    thread_id=target_thread_id,
                    checkpoint_ns=record.checkpoint_ns,
                    checkpoint_id=record.checkpoint_id,
                    parent_checkpoint_id=record.parent_checkpoint_id,
                    checkpoint_payload=copy.deepcopy(record.checkpoint_payload),
                    metadata_payload=copy.deepcopy(record.metadata_payload),
                )
                repository.update_pending_writes(
                    thread_id=target_thread_id,
                    checkpoint_ns=record.checkpoint_ns,
                    checkpoint_id=record.checkpoint_id,
                    pending_writes_payload=copy.deepcopy(record.pending_writes_payload),
                )

    def prune(
        self,
        thread_ids: Sequence[str],
        *,
        strategy: str = "keep_latest",
    ) -> None:
        if strategy == "delete":
            for thread_id in thread_ids:
                self.delete_thread(thread_id)
            return

        if strategy != "keep_latest":
            return

        for thread_id in thread_ids:
            with self.session_factory() as db:
                records = WorkflowCheckpointRepository(db).list(thread_id=thread_id)
            if len(records) <= 1:
                continue
            latest = records[0]
            self.delete_thread(thread_id)
            with self.session_factory() as db:
                repository = WorkflowCheckpointRepository(db)
                repository.save(
                    thread_id=latest.thread_id,
                    checkpoint_ns=latest.checkpoint_ns,
                    checkpoint_id=latest.checkpoint_id,
                    parent_checkpoint_id=latest.parent_checkpoint_id,
                    checkpoint_payload=copy.deepcopy(latest.checkpoint_payload),
                    metadata_payload=copy.deepcopy(latest.metadata_payload),
                )
                repository.update_pending_writes(
                    thread_id=latest.thread_id,
                    checkpoint_ns=latest.checkpoint_ns,
                    checkpoint_id=latest.checkpoint_id,
                    pending_writes_payload=copy.deepcopy(latest.pending_writes_payload),
                )

    def _encode_typed(self, value: Any) -> dict[str, str]:
        kind, payload = self.serde.dumps_typed(value)
        return {
            "kind": kind,
            "payload": base64.b64encode(payload).decode("ascii"),
        }

    def decode_typed_value(self, value: dict[str, str]) -> Any:
        return self._decode_typed(value)

    def _decode_typed(self, value: dict[str, str]) -> Any:
        return self.serde.loads_typed(
            (
                value["kind"],
                base64.b64decode(value["payload"].encode("ascii")),
            )
        )
