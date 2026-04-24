from app.integrations.llamaindex_ingestion import run_document_ingestion_pipeline


def test_run_document_ingestion_pipeline_returns_chunks_with_metadata() -> None:
    text = "员工请假需要提前一天提交申请。紧急情况可补交说明。" * 20

    chunks = run_document_ingestion_pipeline(
        text=text,
        document_id="doc-test-001",
        knowledge_base_id="kb-test-001",
        file_name="请假制度.md",
        file_path="/tmp/leave-policy.md",
        mime_type="text/markdown",
    )

    assert len(chunks) >= 2
    assert chunks[0].chunk_index == 0
    assert chunks[0].content
    assert chunks[0].char_count == len(chunks[0].content)
    assert chunks[0].metadata["document_id"] == "doc-test-001"
    assert chunks[0].metadata["knowledge_base_id"] == "kb-test-001"
    assert chunks[0].metadata["file_name"] == "请假制度.md"
    assert chunks[0].metadata["mime_type"] == "text/markdown"
    assert chunks[0].metadata["ingestion_pipeline"] == "llamaindex_sentence_splitter"
    assert "start_char_idx" in chunks[0].metadata
    assert "end_char_idx" in chunks[0].metadata
