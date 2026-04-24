"""封装服务端使用的 embedding 后端和降级策略。

应用其他部分只依赖 ``EmbeddingService``，
不需要关心向量到底来自：
- 本地 hash embedding
- OpenAI 兼容的远程 embedding 接口
"""

import json
import logging
import ssl
from abc import ABC, abstractmethod
from urllib import error, request

from app.core.config import get_settings
from app.integrations.local_embeddings import embed_text as embed_text_local

logger = logging.getLogger(__name__)


class EmbeddingBackend(ABC):
    """embedding 后端的统一抽象，便于切换 provider。"""

    name: str

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class LocalEmbeddingBackend(EmbeddingBackend):
    """本地 deterministic fallback 后端。

    它不是为了生产检索质量设计的，主要目的是在没有远程 embedding
    服务时，保证本地开发和测试还能继续跑。
    """

    name = "local_hash"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [embed_text_local(text) for text in texts]


class OpenAICompatibleEmbeddingBackend(EmbeddingBackend):
    """调用遵循 OpenAI `/embeddings` 协议的远程接口。"""

    name = "openai_compatible"

    def __init__(self) -> None:
        self.settings = get_settings()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        endpoint = self.settings.embedding_api_base.rstrip("/") + "/embeddings"
        payload = {
            "input": texts,
            "model": self.settings.embedding_model,
            # 有些 OpenAI 兼容服务要求显式传 dimensions。
            "dimensions": self.settings.embedding_dim,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.settings.resolved_embedding_api_key}",
        }
        http_request = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        ssl_context = None
        if not self.settings.embedding_ssl_verify:
            # 适合内网网关或自签名证书环境。
            ssl_context = ssl._create_unverified_context()
        try:
            with request.urlopen(
                http_request,
                timeout=self.settings.embedding_timeout_seconds,
                context=ssl_context,
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"embedding 请求失败，HTTP {exc.code}: {detail[:300]}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"embedding 请求失败：{exc.reason}") from exc

        items = sorted(body.get("data", []), key=lambda item: item.get("index", 0))
        vectors = [item.get("embedding", []) for item in items]
        # 这里做一层防御性校验，避免错误向量静默写入向量库。
        if len(vectors) != len(texts):
            raise RuntimeError("embedding 返回向量数量与输入数量不一致。")
        if any(len(vector) != self.settings.embedding_dim for vector in vectors):
            raise RuntimeError(
                "embedding 返回维度与 EMBEDDING_DIM 不一致，请检查模型或维度配置。"
            )
        return vectors


class EmbeddingService:
    """解析当前实际使用的后端，并处理可选的 fallback 逻辑。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.primary_backend, self.fallback_backend = self._resolve_backends()
        self.active_backend_name = self.primary_backend.name

    def _resolve_backends(self) -> tuple[EmbeddingBackend, EmbeddingBackend | None]:
        provider = self.settings.embedding_provider.lower().strip()
        if provider == "local":
            return LocalEmbeddingBackend(), None

        if provider in {"auto", "openai"} and self.settings.resolved_embedding_api_key:
            # auto 模式下，远程 embedding 挂掉时还能自动回退到本地；
            # openai 模式更严格，不会静默降级。
            fallback_backend = LocalEmbeddingBackend() if provider == "auto" else None
            return OpenAICompatibleEmbeddingBackend(), fallback_backend

        if provider == "openai":
            raise RuntimeError(
                "embedding_provider=openai 但未配置可用的 embedding API key。"
            )

        return LocalEmbeddingBackend(), None

    def describe_backend(self) -> str:
        if self.fallback_backend:
            return f"{self.primary_backend.name} (fallback: {self.fallback_backend.name})"
        return self.active_backend_name

    def embed_text(self, text: str) -> list[float]:
        vectors = self.embed_texts([text])
        return vectors[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        try:
            vectors = self.primary_backend.embed_texts(texts)
            self.active_backend_name = self.primary_backend.name
            return vectors
        except Exception as exc:
            if not self.fallback_backend:
                raise
            # 只有在显式允许 fallback 时才降级，避免上游短暂故障直接打断
            # 文档入库或查询流程。
            logger.warning(
                "primary embedding backend failed, fallback to %s: %s",
                self.fallback_backend.name,
                exc,
            )
            vectors = self.fallback_backend.embed_texts(texts)
            self.active_backend_name = self.fallback_backend.name
            return vectors
