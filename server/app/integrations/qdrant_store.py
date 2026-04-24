"""基于官方 LlamaIndex Vector Store 的 Qdrant chunk 存储层。

这个模块负责：
- 把业务层的 chunk dict 转成 LlamaIndex ``TextNode``
- 通过官方 ``QdrantVectorStore`` 读写向量
- 按知识库暴露 retriever，供上层检索服务组合
"""

from pathlib import Path
from threading import RLock

from llama_index.core import VectorStoreIndex
from llama_index.core.schema import TextNode
from llama_index.core.vector_stores.types import FilterOperator, MetadataFilter, MetadataFilters
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from app.core.config import get_settings
from app.integrations.embedding_provider import EmbeddingService
from app.integrations.llamaindex_embeddings import EmbeddingServiceAdapter


class QdrantChunkStore:
    """封装 Qdrant collection 管理和 LlamaIndex 检索接线。"""

    _LOCAL_CLIENTS: dict[str, QdrantClient] = {}
    _LOCAL_LOCK = RLock()

    def __init__(self) -> None:
        self.settings = get_settings()
        self.collection_name = self.settings.qdrant_collection_name
        self.embedding_service = EmbeddingService()
        self.embedding_adapter = EmbeddingServiceAdapter(self.embedding_service)
        if self.settings.qdrant_use_local:
            qdrant_path = Path(self.settings.qdrant_path)
            qdrant_path.parent.mkdir(parents=True, exist_ok=True)
            client_key = str(qdrant_path.resolve())
            with self._LOCAL_LOCK:
                existing_client = self._LOCAL_CLIENTS.get(client_key)
                if existing_client is None:
                    # 本地 Qdrant 基于文件存储，重复创建 client 容易遇到锁冲突。
                    # 这里按 path 复用 client，并用锁避免批量上传后台任务并发初始化。
                    existing_client = QdrantClient(path=str(qdrant_path))
                    self._LOCAL_CLIENTS[client_key] = existing_client
            self.client = existing_client
        else:
            self.client = QdrantClient(url=self.settings.qdrant_url)

    def _operation_lock(self):
        if self.settings.qdrant_use_local:
            return self._LOCAL_LOCK
        return _NullLock()

    def _resolve_collection_name(self, embedding_backend: str) -> str:
        # 按后端、模型、维度拆 collection，避免不同向量空间的向量混进同一个库。
        model_suffix = self.embedding_service.active_backend_name
        if embedding_backend == "openai_compatible":
            sanitized_model = "".join(
                ch.lower() if ch.isalnum() else "_"
                for ch in self.settings.embedding_model
            ).strip("_")
            model_suffix = sanitized_model or embedding_backend
        return (
            f"{self.collection_name}__{embedding_backend}"
            f"__dim_{self.settings.embedding_dim}"
            f"__{model_suffix}"
        )

    def _ensure_collection(self, collection_name: str) -> None:
        with self._operation_lock():
            if self.client.collection_exists(collection_name):
                return
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=self.settings.embedding_dim,
                    distance=Distance.COSINE,
                ),
            )

    def _get_vector_store(self) -> QdrantVectorStore:
        # 把底层 client 交给官方 QdrantVectorStore 之后，增删查协议就都走
        # LlamaIndex 官方实现。
        return QdrantVectorStore(
            collection_name=self._resolve_collection_name(
                self.embedding_service.active_backend_name
            ),
            client=self.client,
        )

    def _get_index(self) -> VectorStoreIndex:
        # 这里直接从已有 vector store 构造 index，而不是在内存里再建一套新索引。
        return VectorStoreIndex.from_vector_store(
            self._get_vector_store(),
            embed_model=self.embedding_adapter,
        )

    def _to_node(self, chunk: dict) -> TextNode:
        # 来源、引用等字段留在 metadata；MIME type 和字符区间则放进
        # TextNode 的专用字段里。
        metadata = {
            key: value
            for key, value in chunk.items()
            if key not in {"chunk_id", "content", "mime_type", "start_char_idx", "end_char_idx"}
        }
        return TextNode(
            id_=str(chunk["chunk_id"]),
            text=str(chunk["content"]),
            metadata=metadata,
            mimetype=str(chunk.get("mime_type", "text/plain")),
            start_char_idx=_to_optional_int(chunk.get("start_char_idx")),
            end_char_idx=_to_optional_int(chunk.get("end_char_idx")),
        )

    def upsert_chunks(self, chunks: list[dict]) -> None:
        nodes = [
            self._to_node(
                {
                    **chunk,
                    # 记录这次写入实际使用的 embedding 后端，方便后面排查
                    # 检索结果到底来自哪套向量空间。
                    "embedding_backend": self.embedding_service.active_backend_name,
                }
            )
            for chunk in chunks
        ]
        if not nodes:
            return

        # 先通过 adapter 计算 embedding，再把带向量的 node 交给官方
        # vector store 持久化。
        embedded_nodes = list(self.embedding_adapter(nodes))
        with self._operation_lock():
            vector_store = self._get_vector_store()
            vector_store.add(embedded_nodes)

    def delete_chunk_ids(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return

        collection_name = self._resolve_collection_name(
            self.embedding_service.active_backend_name
        )
        with self._operation_lock():
            if not self.client.collection_exists(collection_name):
                return
            self._get_vector_store().delete_nodes(node_ids=chunk_ids)

    def as_retriever(self, knowledge_base_id: str, top_k: int):
        collection_name = self._resolve_collection_name(
            self.embedding_service.active_backend_name
        )
        with self._operation_lock():
            if not self.client.collection_exists(collection_name):
                return None

        # 这一层永远只负责单知识库检索；多知识库组合放在上层 RouterRetriever。
        filters = MetadataFilters(
            filters=[
                MetadataFilter(
                    key="knowledge_base_id",
                    value=knowledge_base_id,
                    operator=FilterOperator.EQ,
                )
            ]
        )
        return self._get_index().as_retriever(
            similarity_top_k=top_k,
            filters=filters,
        )

def _to_optional_int(value) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


class _NullLock:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False
