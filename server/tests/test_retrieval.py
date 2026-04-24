from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

from app.integrations.qdrant_store import QdrantChunkStore
from app.services.retrieval import RetrievalService


class StubRetriever(BaseRetriever):
    def __init__(self, hits: list[dict]) -> None:
        super().__init__()
        self.hits = hits

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        return [
            NodeWithScore(
                node=TextNode(
                    id_=str(hit["chunk_id"]),
                    text=str(hit["content"]),
                    metadata={
                        key: value
                        for key, value in hit.items()
                        if key not in {"content", "score"}
                    },
                ),
                score=float(hit["score"]),
            )
            for hit in self.hits
        ]


class StubChunkStore:
    def __init__(self, hits_by_kb: dict[str, list[dict]]) -> None:
        self.hits_by_kb = hits_by_kb
        self.embedding_service = type(
            "EmbeddingBackendStub",
            (),
            {"active_backend_name": "stub_dense"},
        )()

    def as_retriever(self, knowledge_base_id: str, top_k: int):
        hits = self.hits_by_kb.get(knowledge_base_id, [])[:top_k]
        if not hits:
            return None
        return StubRetriever(hits)


def test_retrieve_reranks_by_lexical_match() -> None:
    store = StubChunkStore(
        {
            "kb-demo-001": [
                {
                    "chunk_id": "chunk-dense-first",
                    "document_id": "doc-001",
                    "knowledge_base_id": "kb-demo-001",
                    "chunk_index": 0,
                    "file_name": "通用制度.md",
                    "content": "这里主要介绍考勤、值班和值守要求。",
                    "vector_score": 0.91,
                    "score": 0.91,
                },
                {
                    "chunk_id": "chunk-lexical-first",
                    "document_id": "doc-002",
                    "knowledge_base_id": "kb-demo-001",
                    "chunk_index": 1,
                    "file_name": "请假制度.md",
                    "content": "员工请假需要提前一天提交申请，紧急情况可补交说明。",
                    "vector_score": 0.76,
                    "score": 0.76,
                },
            ]
        }
    )

    service = RetrievalService(store=store)
    assert "qdrant_vector_store" in service.describe_strategy()
    hits = service.retrieve(
        knowledge_base_id="kb-demo-001",
        query="员工请假需要提前多久提交申请？",
        top_k=2,
    )

    assert hits[0]["chunk_id"] == "chunk-lexical-first"
    assert hits[0]["lexical_score"] > hits[1]["lexical_score"]
    assert hits[0]["score"] > hits[1]["score"]


def test_retrieve_many_uses_router_retriever() -> None:
    store = StubChunkStore(
        {
            "kb-demo-001": [
                {
                    "chunk_id": "chunk-leave",
                    "document_id": "doc-001",
                    "knowledge_base_id": "kb-demo-001",
                    "chunk_index": 0,
                    "file_name": "请假制度.md",
                    "content": "员工请假需要提前一天提交申请。",
                    "vector_score": 0.74,
                    "score": 0.74,
                }
            ],
            "kb-demo-002": [
                {
                    "chunk_id": "chunk-expense",
                    "document_id": "doc-002",
                    "knowledge_base_id": "kb-demo-002",
                    "chunk_index": 0,
                    "file_name": "报销制度.md",
                    "content": "员工报销需要提供发票和审批单。",
                    "vector_score": 0.72,
                    "score": 0.72,
                }
            ],
        }
    )

    service = RetrievalService(store=store)
    hits = service.retrieve_many(
        knowledge_base_ids=["kb-demo-001", "kb-demo-002"],
        query="请总结请假和报销的要求。",
        top_k=2,
        per_kb_top_k=2,
    )

    assert len(hits) == 2
    assert {item["chunk_id"] for item in hits} == {"chunk-leave", "chunk-expense"}
    assert all(item["score"] > 0 for item in hits)


def test_local_qdrant_store_reuses_client_when_created_repeatedly() -> None:
    first_store = QdrantChunkStore()
    second_store = QdrantChunkStore()

    assert first_store.client is second_store.client
