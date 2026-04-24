"""服务层使用的 LlamaIndex 检索辅助组件。

当前检索链路已经接入官方 LlamaIndex 抽象，但路由逻辑仍保持轻量和确定性：
- ``RouterRetriever`` 负责多知识库 fan-out
- ``ExplicitKnowledgeBaseSelector`` 决定哪些检索器参与本轮检索
- ``LexicalRerankPostprocessor`` 用词面重叠对 dense 结果再排序
"""

from typing import Optional, Sequence

from llama_index.core.base.base_selector import MultiSelection, SingleSelection
from llama_index.core.llms.mock import MockLLM
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.retrievers import BaseRetriever, RouterRetriever
from llama_index.core.schema import MetadataMode, NodeWithScore, QueryBundle
from llama_index.core.selectors import BaseSelector
from llama_index.core.tools import RetrieverTool

from app.integrations.local_embeddings import tokenize_text
from app.services.retrieval_ranking import compute_retrieval_score, score_lexical_match


class ExplicitKnowledgeBaseSelector(BaseSelector):
    """给 ``RouterRetriever`` 用的确定性 selector。

    这里故意不接 LLM selector，因为知识库范围在上游已经基本确定，
    当前阶段也不希望检索路由额外依赖一次模型调用。
    """

    def _get_prompts(self) -> dict:
        return {}

    def _get_prompt_modules(self) -> dict:
        return {}

    def _update_prompts(self, prompts_dict: dict) -> None:
        return None

    def _select(self, choices, query: QueryBundle) -> MultiSelection:
        if not choices:
            return MultiSelection(selections=[])

        if len(choices) == 1:
            return MultiSelection(
                selections=[
                    SingleSelection(
                        index=0,
                        reason="当前只有一个知识库候选，直接使用该检索器。",
                    )
                ]
            )

        query_tokens = set(tokenize_text(query.query_str))
        matched_indexes: list[int] = []
        for index, choice in enumerate(choices):
            # 当一次请求里存在多个 retriever 时，先用工具名和描述做一层
            # 低成本的词面路由提示。
            choice_tokens = set(
                tokenize_text(f"{choice.name} {choice.description}")
            )
            if query_tokens.intersection(choice_tokens):
                matched_indexes.append(index)

        if matched_indexes:
            return MultiSelection(
                selections=[
                    SingleSelection(
                        index=index,
                        reason="问题与该知识库工具描述存在词面重叠，纳入路由检索范围。",
                    )
                    for index in matched_indexes
                ]
            )

        return MultiSelection(
            selections=[
                SingleSelection(
                    index=index,
                    reason="知识库范围已在上游确定，本轮保留该候选检索器参与路由。",
                )
                for index, _choice in enumerate(choices)
            ]
        )

    async def _aselect(self, choices, query: QueryBundle) -> MultiSelection:
        return self._select(choices, query)


class LexicalRerankPostprocessor(BaseNodePostprocessor):
    """在最终截断 top-k 前，把 dense 分数和词面分数混合重排。"""

    top_k: int = 4

    def _postprocess_nodes(
        self,
        nodes: list[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
    ) -> list[NodeWithScore]:
        query = query_bundle.query_str if query_bundle else ""
        reranked: list[NodeWithScore] = []

        for item in nodes:
            # 先复制一份 node，再补充重排后的 metadata，避免直接修改
            # retriever 返回的原始对象。
            node = item.node.model_copy(deep=True)
            metadata = dict(node.metadata or {})
            content = node.get_content(metadata_mode=MetadataMode.NONE).strip()
            vector_score = float(metadata.get("vector_score", item.score or 0.0))
            lexical_score = score_lexical_match(
                query,
                content,
                file_name=str(metadata.get("file_name", "")),
            )
            score = compute_retrieval_score(
                vector_score=vector_score,
                lexical_score=lexical_score,
            )

            metadata["vector_score"] = round(vector_score, 6)
            metadata["lexical_score"] = round(lexical_score, 6)
            metadata["score"] = round(score, 6)
            node.metadata = metadata
            reranked.append(NodeWithScore(node=node, score=score))

        reranked.sort(
            key=lambda item: (
                -float(item.score or 0.0),
                -float(item.node.metadata.get("lexical_score", 0.0)),
                -float(item.node.metadata.get("vector_score", 0.0)),
                str(item.node.metadata.get("knowledge_base_id", "")),
                int(item.node.metadata.get("chunk_index", 0)),
            )
        )
        return reranked[: self.top_k]


def build_router_retriever(retriever_tools: Sequence[RetrieverTool]) -> BaseRetriever:
    # RouterRetriever 要求传 llm，但当前选择逻辑已经由上面的
    # ExplicitKnowledgeBaseSelector 全部接管，所以这里用 MockLLM 占位。
    return RouterRetriever(
        selector=ExplicitKnowledgeBaseSelector(),
        retriever_tools=retriever_tools,
        llm=MockLLM(),
    )
