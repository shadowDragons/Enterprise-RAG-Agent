from llama_index.core.schema import MetadataMode, NodeWithScore, QueryBundle
from llama_index.core.tools import RetrieverTool

from app.core.config import get_settings
from app.integrations.llamaindex_retrieval import (
    LexicalRerankPostprocessor,
    build_router_retriever,
)
from app.integrations.qdrant_store import QdrantChunkStore


class RetrievalService:
    def __init__(self, store: QdrantChunkStore | None = None) -> None:
        self.settings = get_settings()
        self.store = store or QdrantChunkStore()

    def describe_strategy(self) -> str:
        return (
            "llamaindex qdrant_vector_store + router_retriever + lexical_rerank "
            f"(embedding={self.store.embedding_service.active_backend_name})"
        )

    def _candidate_limit(self, top_k: int) -> int:
        factor = max(1, self.settings.retrieval_overfetch_factor)
        return max(top_k, top_k * factor)

    def _rerank_nodes(
        self,
        *,
        query: str,
        nodes: list[NodeWithScore],
        top_k: int,
    ) -> list[NodeWithScore]:
        postprocessor = LexicalRerankPostprocessor(top_k=top_k)
        return postprocessor.postprocess_nodes(
            nodes,
            query_bundle=QueryBundle(query_str=query),
        )

    def _node_to_hit(self, item: NodeWithScore) -> dict:
        metadata = dict(item.node.metadata or {})
        return {
            "chunk_id": str(metadata.get("chunk_id", item.node.node_id)),
            "document_id": str(metadata.get("document_id", "")),
            "knowledge_base_id": str(metadata.get("knowledge_base_id", "")),
            "chunk_index": int(metadata.get("chunk_index", 0)),
            "file_name": str(metadata.get("file_name", "")),
            "content": item.node.get_content(metadata_mode=MetadataMode.NONE).strip(),
            "score": round(float(metadata.get("score", item.score or 0.0)), 6),
            "vector_score": round(
                float(metadata.get("vector_score", item.score or 0.0)),
                6,
            ),
            "lexical_score": round(float(metadata.get("lexical_score", 0.0)), 6),
            "embedding_backend": str(metadata.get("embedding_backend", "")),
        }

    def retrieve(
        self,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[dict]:
        retriever = self.store.as_retriever(
            knowledge_base_id=knowledge_base_id,
            top_k=self._candidate_limit(top_k),
        )
        if retriever is None:
            return []

        nodes = retriever.retrieve(query)
        reranked_nodes = self._rerank_nodes(query=query, nodes=nodes, top_k=top_k)
        return [self._node_to_hit(item) for item in reranked_nodes]

    def retrieve_many(
        self,
        knowledge_base_ids: list[str],
        query: str,
        top_k: int,
        per_kb_top_k: int | None = None,
    ) -> list[dict]:
        unique_kb_ids = list(dict.fromkeys(kb_id for kb_id in knowledge_base_ids if kb_id))
        if not unique_kb_ids:
            return []

        limit = per_kb_top_k or top_k
        retriever_tools: list[RetrieverTool] = []
        for knowledge_base_id in unique_kb_ids:
            retriever = self.store.as_retriever(
                knowledge_base_id=knowledge_base_id,
                top_k=self._candidate_limit(limit),
            )
            if retriever is None:
                continue
            retriever_tools.append(
                RetrieverTool.from_defaults(
                    retriever=retriever,
                    name=f"knowledge_base_{knowledge_base_id}",
                    description=f"仅检索知识库 {knowledge_base_id} 下的文档片段。",
                )
            )

        if not retriever_tools:
            return []

        router_retriever = build_router_retriever(retriever_tools)
        nodes = router_retriever.retrieve(query)
        reranked_nodes = self._rerank_nodes(query=query, nodes=nodes, top_k=top_k)
        return [self._node_to_hit(item) for item in reranked_nodes]
