import re
from datetime import datetime
from typing import Literal

from app.core.review_rules import default_review_rules
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ReviewRuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(min_length=1, max_length=64)
    rule_name: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=64)
    severity: Literal["low", "medium", "high", "critical"] = "high"
    priority: int = 100
    enabled: bool = True
    match_mode: Literal["contains_any", "contains_all", "regex"] = "contains_any"
    keywords: list[str] = Field(default_factory=list)
    regex_pattern: str = Field(default="", max_length=512)

    @field_validator("rule_id", "rule_name", "category", "regex_pattern")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("keywords")
    @classmethod
    def _normalize_keywords(cls, value: list[str]) -> list[str]:
        normalized_keywords: list[str] = []
        seen: set[str] = set()
        for item in value:
            keyword = str(item).strip()
            if not keyword:
                continue
            normalized_key = keyword.lower()
            if normalized_key in seen:
                continue
            normalized_keywords.append(keyword)
            seen.add(normalized_key)
        return normalized_keywords

    @model_validator(mode="after")
    def _validate_match_config(self) -> "ReviewRuleConfig":
        if self.match_mode == "regex":
            if not self.regex_pattern:
                raise ValueError("正则匹配模式必须提供 regex_pattern。")
            try:
                re.compile(self.regex_pattern, flags=re.IGNORECASE)
            except re.error as exc:
                raise ValueError(f"regex_pattern 非法：{exc.msg}") from exc
            self.keywords = []
            return self

        if not self.keywords:
            raise ValueError("关键词匹配模式至少需要一个关键词。")
        self.regex_pattern = ""
        return self


class AssistantConfigPayload(BaseModel):
    assistant_name: str = Field(min_length=1, max_length=255)
    description: str = ""
    system_prompt: str = ""
    default_model: str = "gpt-4o"
    default_kb_ids: list[str] = Field(default_factory=list)
    tool_keys: list[str] = Field(default_factory=list)
    review_rules: list[ReviewRuleConfig] = Field(default_factory=default_review_rules)
    review_enabled: bool = False

    @model_validator(mode="after")
    def _validate_review_rules(self) -> "AssistantConfigPayload":
        if self.review_enabled and not self.review_rules:
            raise ValueError("启用审核时至少需要配置一条审核规则。")
        return self


class AssistantCreate(AssistantConfigPayload):
    pass


class AssistantUpdate(AssistantConfigPayload):
    change_note: str = Field(default="", max_length=1000)


class AssistantRestoreVersionRequest(BaseModel):
    change_note: str = Field(default="", max_length=1000)


class AssistantSummary(AssistantConfigPayload):
    model_config = ConfigDict(from_attributes=True)

    assistant_id: str
    default_kb_count: int
    session_count: int
    review_rule_count: int
    version: int
    created_at: datetime
    updated_at: datetime


class AssistantVersionSnapshot(AssistantConfigPayload):
    version: int


class AssistantVersionSummary(BaseModel):
    assistant_id: str
    version: int
    change_note: str
    created_at: datetime
    snapshot: AssistantVersionSnapshot


class AssistantVersionDetail(AssistantVersionSummary):
    assistant_version_id: str


class AssistantDeleteResult(BaseModel):
    assistant_id: str
    deleted_session_count: int
    deleted_review_count: int
    deleted_audit_log_count: int
    deleted_checkpoint_count: int


def to_assistant_summary(assistant, *, session_count: int = 0) -> AssistantSummary:
    return AssistantSummary(
        assistant_id=assistant.assistant_id,
        assistant_name=assistant.assistant_name,
        description=assistant.description,
        default_model=assistant.default_model,
        default_kb_ids=assistant.default_kb_ids,
        default_kb_count=len(assistant.default_kb_ids),
        session_count=session_count,
        review_enabled=assistant.review_enabled,
        review_rules=assistant.review_rules,
        review_rule_count=len(assistant.review_rules or []),
        version=assistant.version,
        created_at=assistant.created_at,
        updated_at=assistant.updated_at,
    )


def to_assistant_version_snapshot(snapshot_payload: dict) -> AssistantVersionSnapshot:
    normalized_payload = dict(snapshot_payload or {})
    return AssistantVersionSnapshot(
        assistant_name=str(normalized_payload.get("assistant_name", "")),
        description=str(normalized_payload.get("description", "")),
        system_prompt=str(normalized_payload.get("system_prompt", "")),
        default_model=str(normalized_payload.get("default_model", "gpt-4o")),
        default_kb_ids=list(normalized_payload.get("default_kb_ids", [])),
        tool_keys=list(normalized_payload.get("tool_keys", [])),
        review_rules=list(normalized_payload.get("review_rules", [])),
        review_enabled=bool(normalized_payload.get("review_enabled", False)),
        version=int(normalized_payload.get("version", 1)),
    )


def to_assistant_version_summary(assistant_version) -> AssistantVersionSummary:
    return AssistantVersionSummary(
        assistant_id=assistant_version.assistant_id,
        version=assistant_version.version,
        change_note=assistant_version.change_note,
        created_at=assistant_version.created_at,
        snapshot=to_assistant_version_snapshot(assistant_version.snapshot_payload),
    )


def to_assistant_version_detail(assistant_version) -> AssistantVersionDetail:
    return AssistantVersionDetail(
        **to_assistant_version_summary(assistant_version).model_dump(),
        assistant_version_id=assistant_version.assistant_version_id,
    )
