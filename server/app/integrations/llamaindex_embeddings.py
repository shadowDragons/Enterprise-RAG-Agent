"""把现有 embedding 服务适配到 LlamaIndex 的 embedding 接口上。"""

from llama_index.core.base.embeddings.base import BaseEmbedding

from app.integrations.embedding_provider import EmbeddingService


class EmbeddingServiceAdapter(BaseEmbedding):
    """让 LlamaIndex 复用现有 embedding 配置和后端实现。"""

    model_name: str = "embedding_service_adapter"

    def __init__(self, embedding_service: EmbeddingService) -> None:
        super().__init__(
            model_name=f"embedding_service::{embedding_service.settings.embedding_model}"
        )
        self._embedding_service = embedding_service

    def _get_query_embedding(self, query: str) -> list[float]:
        # 当前项目里 query 和 document 使用同一套 embedding 后端。
        return self._embedding_service.embed_text(query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._embedding_service.embed_text(text)

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        # 批量 embedding 很重要。入库阶段通常会一次处理很多 chunk，
        # 一次远程请求通常比逐条请求便宜且稳定。
        return self._embedding_service.embed_texts(texts)
