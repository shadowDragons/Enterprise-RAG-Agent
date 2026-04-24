from app.core.config import get_settings
from app.repositories.assistant_versions import AssistantVersionRepository
from app.repositories.assistants import AssistantRepository
from app.repositories.knowledge_bases import KnowledgeBaseRepository


def build_assistant_snapshot_payload(assistant) -> dict:
    return {
        "assistant_name": assistant.assistant_name,
        "description": assistant.description,
        "system_prompt": assistant.system_prompt,
        "default_model": assistant.default_model,
        "default_kb_ids": list(assistant.default_kb_ids or []),
        "tool_keys": list(assistant.tool_keys or []),
        "review_rules": list(assistant.review_rules or []),
        "review_enabled": bool(assistant.review_enabled),
        "version": int(assistant.version),
    }


class AssistantConfigStateError(RuntimeError):
    def __init__(self, detail: str, *, status_code: int) -> None:
        super().__init__(detail)
        self.status_code = status_code


class AssistantConfigService:
    def __init__(self, db) -> None:
        self.settings = get_settings()
        self.assistant_repository = AssistantRepository(db)
        self.assistant_version_repository = AssistantVersionRepository(db)
        self.knowledge_base_repository = KnowledgeBaseRepository(db)

    def create(self, payload):
        normalized_kb_ids = self._normalize_default_kb_ids(payload.default_kb_ids)
        self._ensure_default_model_allowed(payload.default_model)
        self._ensure_knowledge_bases_exist(normalized_kb_ids)
        assistant = self.assistant_repository.create(
            payload,
            normalized_kb_ids=normalized_kb_ids,
        )
        self.assistant_version_repository.create(
            assistant_id=assistant.assistant_id,
            version=assistant.version,
            change_note="初始化版本",
            snapshot_payload=build_assistant_snapshot_payload(assistant),
        )
        return assistant

    def update(self, assistant_id: str, payload):
        assistant = self._require_assistant(assistant_id)
        normalized_kb_ids = self._normalize_default_kb_ids(payload.default_kb_ids)
        self._ensure_default_model_allowed(payload.default_model)
        self._ensure_knowledge_bases_exist(normalized_kb_ids)
        assistant = self.assistant_repository.update(
            assistant,
            payload,
            normalized_kb_ids=normalized_kb_ids,
        )
        self.assistant_version_repository.create(
            assistant_id=assistant.assistant_id,
            version=assistant.version,
            change_note=payload.change_note.strip() or "更新助理配置",
            snapshot_payload=build_assistant_snapshot_payload(assistant),
        )
        return assistant

    def list_versions(self, assistant_id: str) -> list:
        self._require_assistant(assistant_id)
        return self.assistant_version_repository.list(assistant_id)

    def get_version(self, assistant_id: str, version: int):
        self._require_assistant(assistant_id)
        assistant_version = self.assistant_version_repository.get(assistant_id, version)
        if assistant_version is None:
            raise AssistantConfigStateError(
                f"助理版本不存在：v{version}",
                status_code=404,
            )
        return assistant_version

    def restore_version(
        self,
        assistant_id: str,
        version: int,
        *,
        change_note: str = "",
    ):
        assistant = self._require_assistant(assistant_id)
        assistant_version = self.get_version(assistant_id, version)
        snapshot_payload = dict(assistant_version.snapshot_payload or {})
        normalized_kb_ids = self._normalize_default_kb_ids(
            snapshot_payload.get("default_kb_ids", [])
        )
        self._ensure_default_model_allowed(
            str(snapshot_payload.get("default_model", ""))
        )
        self._ensure_knowledge_bases_exist(normalized_kb_ids)
        assistant = self.assistant_repository.restore_snapshot(
            assistant,
            snapshot_payload=snapshot_payload,
            normalized_kb_ids=normalized_kb_ids,
        )
        self.assistant_version_repository.create(
            assistant_id=assistant.assistant_id,
            version=assistant.version,
            change_note=change_note.strip() or f"从版本 v{version} 恢复",
            snapshot_payload=build_assistant_snapshot_payload(assistant),
        )
        return assistant

    def _require_assistant(self, assistant_id: str):
        assistant = self.assistant_repository.get(assistant_id)
        if assistant is None:
            raise AssistantConfigStateError("助理不存在。", status_code=404)
        return assistant

    def _normalize_default_kb_ids(self, default_kb_ids: list[str]) -> list[str]:
        return list(
            dict.fromkeys(
                item.strip() for item in default_kb_ids if item and item.strip()
            )
        )

    def _ensure_knowledge_bases_exist(self, knowledge_base_ids: list[str]) -> None:
        for knowledge_base_id in knowledge_base_ids:
            knowledge_base = self.knowledge_base_repository.get(knowledge_base_id)
            if knowledge_base is None:
                raise AssistantConfigStateError(
                    f"知识库不存在：{knowledge_base_id}",
                    status_code=404,
                )

    def _ensure_default_model_allowed(self, default_model: str) -> None:
        normalized_model = str(default_model or "").strip()
        allowed_models = [
            item.strip()
            for item in self.settings.llm_allowed_models
            if str(item).strip()
        ]
        if not normalized_model:
            raise AssistantConfigStateError("默认模型不能为空。", status_code=422)
        if allowed_models and normalized_model not in allowed_models:
            allowed_label = "、".join(allowed_models)
            raise AssistantConfigStateError(
                f"默认模型不在允许列表中：{normalized_model}。当前允许：{allowed_label}",
                status_code=422,
            )
