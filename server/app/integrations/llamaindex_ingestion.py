"""使用 LlamaIndex 的 ingestion pipeline 生成文档切块。

这个模块只做一件事：
- 把原始文本包装成 LlamaIndex Document
- 交给 LlamaIndex 做分块
- 再把分块结果整理回我们自己的轻量数据结构
"""

from dataclasses import dataclass

from llama_index.core import Document as LlamaDocument
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import MetadataMode, NodeRelationship


@dataclass(frozen=True)
class IngestedChunk:
    """服务层和仓储层统一使用的切块结构。"""

    chunk_index: int
    content: str
    char_count: int
    metadata: dict[str, str | int]


def build_document_ingestion_pipeline() -> IngestionPipeline:
    """创建文档入库时使用的 LlamaIndex 分块流水线。"""

    return IngestionPipeline(
        transformations=[
            SentenceSplitter(
                # chunk 不宜过大，否则检索粒度太粗；保留少量 overlap，
                # 避免相邻语义被硬切开后丢失上下文。
                chunk_size=300,
                chunk_overlap=50,
            )
        ]
    )


def run_document_ingestion_pipeline(
    *,
    text: str,
    document_id: str,
    knowledge_base_id: str,
    file_name: str,
    file_path: str,
    mime_type: str,
) -> list[IngestedChunk]:
    """运行 LlamaIndex 流水线，并转换成应用内部的 chunk 结构。"""

    pipeline = build_document_ingestion_pipeline()
    source_document = LlamaDocument(text=text)
    nodes = pipeline.run(documents=[source_document])

    chunks: list[IngestedChunk] = []
    for index, node in enumerate(nodes):
        # content 只保留纯文本，其他检索相关信息都走 metadata。
        content = node.get_content(metadata_mode=MetadataMode.NONE).strip()
        if not content:
            continue

        metadata: dict[str, str | int] = {
            "document_id": document_id,
            "knowledge_base_id": knowledge_base_id,
            "file_name": file_name,
            "file_path": file_path,
            "mime_type": mime_type,
            "ingestion_pipeline": "llamaindex_sentence_splitter",
        }
        # LlamaIndex 会把原文中的字符区间挂在 node 上。
        # 这里把它存下来，后续 API 才能标注引用片段来自原文的哪个位置。
        start_char_idx = getattr(node, "start_char_idx", None)
        end_char_idx = getattr(node, "end_char_idx", None)
        if start_char_idx is not None:
            metadata["start_char_idx"] = int(start_char_idx)
        if end_char_idx is not None:
            metadata["end_char_idx"] = int(end_char_idx)

        # SOURCE 指回这次流水线里最初生成的源文档节点。
        # 这个 id 主要用于排查和追踪，检索本身并不依赖它。
        source_node = getattr(node, "relationships", {}).get(NodeRelationship.SOURCE)
        if source_node and getattr(source_node, "node_id", None):
            metadata["source_node_id"] = str(source_node.node_id)

        chunks.append(
            IngestedChunk(
                chunk_index=index,
                content=content,
                char_count=len(content),
                metadata=metadata,
            )
        )

    return chunks
