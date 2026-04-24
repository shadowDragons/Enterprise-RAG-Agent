import os
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "企业级RAG智能助手"
    app_version: str = "0.1.0"
    app_env: str = "dev"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./storage/enterprise_rag.db"
    database_schema_strategy: str = "auto"
    database_pool_size: int = Field(default=10, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=20, alias="DATABASE_MAX_OVERFLOW")
    database_pool_timeout: int = Field(default=30, alias="DATABASE_POOL_TIMEOUT")
    qdrant_use_local: bool = True
    qdrant_url: str = "http://localhost:6333"
    qdrant_path: str = "./storage/qdrant"
    qdrant_collection_name: str = "document_chunks"
    embedding_provider: str = "auto"
    embedding_allowed_models: list[str] = Field(
        default_factory=lambda: ["BAAI/bge-large-zh-v1.5"],
        alias="EMBEDDING_ALLOWED_MODELS",
    )
    embedding_dim: int = Field(default=1024, alias="OPENAI_EMBEDDING_DIMENSIONS")
    embedding_model: str = Field(
        default="BAAI/bge-large-zh-v1.5",
        alias="OPENAI_EMBEDDING_MODEL_NAME",
    )
    embedding_api_base: str = Field(
        default="https://api.siliconflow.cn/v1",
        alias="OPENAI_EMBEDDING_BASE_URL",
    )
    embedding_api_key: str = Field(default="", alias="OPENAI_EMBEDDING_API_KEY")
    embedding_api_key_env_var: str = Field(
        default="SILICONFLOW_API_KEY",
        alias="OPENAI_EMBEDDING_API_KEY_ENV_VAR",
    )
    embedding_timeout_seconds: int = Field(
        default=30,
        alias="OPENAI_EMBEDDING_REQUEST_TIMEOUT_SECONDS",
    )
    embedding_ssl_verify: bool = Field(
        default=True,
        alias="OPENAI_EMBEDDING_SSL_VERIFY",
    )
    llm_provider: str = "auto"
    llm_allowed_models: list[str] = Field(
        default_factory=lambda: ["gpt-4o-mini", "gpt-4o", "gpt-4.1"],
        alias="LLM_ALLOWED_MODELS",
    )
    llm_model: str = Field(default="gpt-4o-mini", alias="OPENAI_LLM_MODEL_NAME")
    llm_api_base: str = Field(default="", alias="OPENAI_LLM_BASE_URL")
    llm_api_key: str = Field(default="", alias="OPENAI_LLM_API_KEY")
    llm_api_key_env_var: str = Field(default="", alias="OPENAI_LLM_API_KEY_ENV_VAR")
    llm_timeout_seconds: int = Field(
        default=60,
        alias="OPENAI_LLM_REQUEST_TIMEOUT_SECONDS",
    )
    llm_ssl_verify: bool = Field(
        default=True,
        alias="OPENAI_LLM_SSL_VERIFY",
    )
    llm_temperature: float = Field(default=0.2, alias="OPENAI_LLM_TEMPERATURE")
    llm_max_context_citations: int = Field(
        default=6,
        alias="OPENAI_LLM_MAX_CONTEXT_CITATIONS",
    )
    production_like_envs: list[str] = Field(
        default_factory=lambda: ["staging", "prod", "production"],
        alias="PRODUCTION_LIKE_ENVS",
    )
    chat_memory_message_window: int = 6
    max_chat_selected_kb_count: int = 3
    retrieval_per_kb_top_k: int = 4
    retrieval_overfetch_factor: int = 3
    retrieval_dense_weight: float = 0.65
    retrieval_lexical_weight: float = 0.35
    workflow_checkpointer_backend: str = "auto"
    workflow_checkpointer_postgres_url: str = ""
    storage_root: str = "./storage"
    system_job_batch_retry_limit: int = Field(default=20, alias="SYSTEM_JOB_BATCH_RETRY_LIMIT")
    auth_enabled: bool = True
    auth_secret_key: str = "change-this-in-production"
    auth_access_token_expire_minutes: int = 480
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5175",
            "http://127.0.0.1:5175",
        ]
    )
    default_stage: str = "M1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator(
        "embedding_allowed_models",
        "llm_allowed_models",
        "production_like_envs",
        mode="before",
    )
    @classmethod
    def _normalize_string_list(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return value

    @property
    def is_production_like(self) -> bool:
        return self.app_env.strip().lower() in {
            item.strip().lower() for item in self.production_like_envs
        }

    @property
    def uses_default_auth_secret(self) -> bool:
        return self.auth_secret_key.strip() == "change-this-in-production"

    @property
    def resolved_embedding_api_key(self) -> str:
        if self.embedding_api_key:
            return self.embedding_api_key
        env_var_name = self.embedding_api_key_env_var.strip()
        if env_var_name:
            return os.getenv(env_var_name, "")
        return ""

    @property
    def resolved_llm_api_base(self) -> str:
        return self.llm_api_base.strip() or self.embedding_api_base.strip()

    @property
    def resolved_llm_api_key(self) -> str:
        if self.llm_api_key:
            return self.llm_api_key
        env_var_name = self.llm_api_key_env_var.strip()
        if env_var_name:
            return os.getenv(env_var_name, "")
        return self.resolved_embedding_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
