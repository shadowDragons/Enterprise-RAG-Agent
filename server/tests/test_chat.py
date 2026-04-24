from fastapi.testclient import TestClient

from app.core.review_rules import default_review_rules
from app.services.answer_generation import AnswerGenerationUnavailableError
from tests.helpers import stream_chat_and_collect_completed


def test_session_chat_and_messages(client: TestClient) -> None:
    client.post(
        "/api/v1/knowledge-bases/kb-demo-001/documents/upload",
        files={
            "file": (
                "员工制度说明.md",
                "员工请假需要提前一天提交申请，紧急情况可补交说明。".encode("utf-8"),
                "text/markdown",
            )
        },
    )

    session_response = client.post(
        "/api/v1/sessions",
        json={
            "assistant_id": "asst-demo-001",
            "title": "制度聊天测试",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    _, chat_data = stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "员工请假需要做什么？",
            "top_k": 3,
        },
    )
    assert chat_data["session_id"] == session_id
    assert chat_data["selected_knowledge_base_id"] == "kb-demo-001"
    assert chat_data["selected_kb_ids"] == ["kb-demo-001"]
    assert chat_data["retrieval_count"] >= 1
    assert "员工请假" in chat_data["answer"]
    assert len(chat_data["workflow_trace"]) >= 4
    assert chat_data["citations"][0]["embedding_backend"] in {
        "local_hash",
        "openai_compatible",
    }
    assert "vector_score" in chat_data["citations"][0]
    assert "lexical_score" in chat_data["citations"][0]
    assert chat_data["workflow_trace"][2]["node"] == "question_intake"
    assert chat_data["workflow_trace"][3]["node"] == "memory_manager"
    assert chat_data["workflow_trace"][4]["node"] == "clarification_router"
    assert chat_data["workflow_trace"][5]["node"] == "intent_guard"
    assert (
        "qdrant_vector_store + router_retriever + lexical_rerank"
        in chat_data["workflow_trace"][6]["detail"]
    )

    messages_response = client.get(f"/api/v1/sessions/{session_id}/messages")
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert len(messages[1]["citations"]) >= 1

    session_detail_response = client.get(f"/api/v1/sessions/{session_id}")
    assert session_detail_response.status_code == 200
    session_detail = session_detail_response.json()
    assert session_detail["status"] == "active"
    assert session_detail["workflow_runtime"]["workflow_thread_id"]
    assert session_detail["workflow_runtime"]["workflow_checkpoint_id"]
    assert session_detail["workflow_runtime"]["runtime_reason"] is None
    assert (
        session_detail["workflow_runtime"]["resolved_question"]
        == "员工请假需要做什么？"
    )
    assert session_detail["workflow_runtime"]["runtime_schema_version"] == 3
    assert session_detail["workflow_runtime"]["runtime_state"] == "completed"
    assert session_detail["workflow_runtime"]["runtime_label"] == "本轮已完成"
    assert session_detail["workflow_runtime"]["waiting_for"] is None
    assert session_detail["workflow_runtime"]["resume_strategy"] == "none"
    assert session_detail["workflow_runtime"]["latest_node"] == "compose_answer"
    assert session_detail["workflow_runtime"]["workflow_source"] == "loop"
    assert session_detail["workflow_runtime"]["workflow_step"] is not None
    assert session_detail["workflow_runtime"]["workflow_checkpoint_backend"] == (
        "database"
    )
    assert session_detail["workflow_runtime"]["checkpoint_status"] == "settled"
    assert session_detail["workflow_runtime"]["checkpoint_label"] == "checkpoint 已落盘"
    assert session_detail["workflow_runtime"]["workflow_pending_write_count"] == 0
    assert session_detail["workflow_runtime"]["workflow_can_resume"] is False


def test_session_chat_with_multiple_knowledge_bases(client: TestClient) -> None:
    create_kb_response = client.post(
        "/api/v1/knowledge-bases",
        json={
            "knowledge_base_name": "报销制度知识库",
            "description": "报销制度测试知识库。",
            "default_retrieval_top_k": 5,
        },
    )
    assert create_kb_response.status_code == 201
    second_kb_id = create_kb_response.json()["knowledge_base_id"]

    client.post(
        "/api/v1/knowledge-bases/kb-demo-001/documents/upload",
        files={
            "file": (
                "请假制度.md",
                "员工请假需要提前一天提交申请。".encode("utf-8"),
                "text/markdown",
            )
        },
    )
    client.post(
        f"/api/v1/knowledge-bases/{second_kb_id}/documents/upload",
        files={
            "file": (
                "报销制度.md",
                "员工报销需要提供发票和审批单。".encode("utf-8"),
                "text/markdown",
            )
        },
    )

    session_response = client.post(
        "/api/v1/sessions",
        json={
            "assistant_id": "asst-demo-001",
            "title": "多知识库聊天测试",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    _, chat_data = stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "请总结请假和报销要求。",
            "knowledge_base_ids": ["kb-demo-001", second_kb_id],
            "top_k": 4,
        },
    )
    assert chat_data["selected_kb_ids"] == ["kb-demo-001", second_kb_id]
    assert chat_data["selected_knowledge_base_id"] == "kb-demo-001"
    assert len(chat_data["citations"]) >= 2
    assert {item["knowledge_base_id"] for item in chat_data["citations"]} == {
        "kb-demo-001",
        second_kb_id,
    }
    assert "请假和报销" in chat_data["answer"]


def test_session_chat_returns_no_hit_answer_without_fallback_reason(
    client: TestClient,
    monkeypatch,
) -> None:
    def fake_retrieve(
        self,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[dict]:
        return []

    monkeypatch.setattr(
        "app.services.retrieval.RetrievalService.retrieve",
        fake_retrieve,
    )

    session_response = client.post(
        "/api/v1/sessions",
        json={
            "assistant_id": "asst-demo-001",
            "title": "无命中测试",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    _, chat_data = stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "完全无关的问题",
            "top_k": 3,
        },
    )

    assert chat_data["retrieval_count"] == 0
    assert chat_data["citations"] == []
    assert chat_data["fallback_reason"] is None
    assert "没有在知识库范围 kb-demo-001 中检索到" in chat_data["answer"]
    assert chat_data["workflow_trace"][-2]["node"] == "retrieval"
    assert chat_data["workflow_trace"][-1]["node"] == "compose_answer"


def test_session_chat_marks_clarification_runtime_when_topic_drift_is_detected(
    client: TestClient,
) -> None:
    client.post(
        "/api/v1/knowledge-bases/kb-demo-001/documents/upload",
        files={
            "file": (
                "员工制度说明.md",
                "员工请假需要提前一天提交申请，紧急情况可补交说明。".encode("utf-8"),
                "text/markdown",
            )
        },
    )

    session_response = client.post(
        "/api/v1/sessions",
        json={
            "assistant_id": "asst-demo-001",
            "title": "澄清运行态测试",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "员工请假需要做什么？",
            "top_k": 3,
        },
    )

    _, second_chat_data = stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "团建预算怎么申请？",
            "top_k": 3,
        },
    )
    assert second_chat_data["fallback_reason"] == "intent_clarification_required"

    session_detail_response = client.get(f"/api/v1/sessions/{session_id}")
    assert session_detail_response.status_code == 200
    session_detail = session_detail_response.json()
    assert session_detail["status"] == "awaiting_clarification"
    assert session_detail["workflow_runtime"]["workflow_thread_id"]
    assert session_detail["workflow_runtime"]["workflow_checkpoint_id"]
    assert (
        "等待用户确认是否切换主题"
        in session_detail["workflow_runtime"]["runtime_reason"]
    )
    assert (
        session_detail["workflow_runtime"]["current_goal"]
        == "员工请假需要做什么？"
    )
    assert (
        session_detail["workflow_runtime"]["pending_question"]
        == "团建预算怎么申请？"
    )
    assert (
        session_detail["workflow_runtime"]["clarification_stage"]
        == "confirm_switch"
    )
    assert (
        session_detail["workflow_runtime"]["clarification_expected_input"]
        == "topic_switch_confirmation"
    )
    assert session_detail["workflow_runtime"]["pending_review_id"] is None
    assert (
        session_detail["workflow_runtime"]["runtime_state"]
        == "waiting_clarification_switch"
    )
    assert session_detail["workflow_runtime"]["waiting_for"] == (
        "topic_switch_confirmation"
    )
    assert session_detail["workflow_runtime"]["resume_strategy"] == "new_user_message"
    assert session_detail["workflow_runtime"]["latest_node"] == "compose_answer"
    assert session_detail["workflow_runtime"]["workflow_source"] == "loop"


def test_session_chat_marks_new_topic_question_runtime_after_explicit_switch_without_question(
    client: TestClient,
) -> None:
    client.post(
        "/api/v1/knowledge-bases/kb-demo-001/documents/upload",
        files={
            "file": (
                "员工制度说明.md",
                (
                    "员工请假需要提前一天提交申请。\n"
                    "团建预算需要先提交活动方案，再走部门审批。"
                ).encode("utf-8"),
                "text/markdown",
            )
        },
    )

    session_response = client.post(
        "/api/v1/sessions",
        json={
            "assistant_id": "asst-demo-001",
            "title": "显式切换待补问题测试",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "员工请假需要做什么？",
            "top_k": 3,
        },
    )

    _, second_chat_data = stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "换个问题",
            "top_k": 3,
        },
    )
    assert second_chat_data["fallback_reason"] == "intent_clarification_required"
    assert "准备切换到新主题" in second_chat_data["answer"]

    session_detail_response = client.get(f"/api/v1/sessions/{session_id}")
    assert session_detail_response.status_code == 200
    session_detail = session_detail_response.json()
    assert session_detail["status"] == "awaiting_clarification"
    assert (
        "当前消息未包含新主题的具体问题"
        in session_detail["workflow_runtime"]["runtime_reason"]
    )
    assert (
        session_detail["workflow_runtime"]["current_goal"]
        == "员工请假需要做什么？"
    )
    assert (
        session_detail["workflow_runtime"]["clarification_type"]
        == "new_topic_question"
    )
    assert (
        session_detail["workflow_runtime"]["clarification_stage"]
        == "collect_new_topic_question"
    )
    assert (
        session_detail["workflow_runtime"]["clarification_expected_input"]
        == "new_topic_question"
    )
    assert session_detail["workflow_runtime"]["pending_question"] is None
    assert (
        session_detail["workflow_runtime"]["runtime_state"]
        == "waiting_new_topic_question"
    )
    assert session_detail["workflow_runtime"]["waiting_for"] == "new_topic_question"
    assert session_detail["workflow_runtime"]["resume_strategy"] == "new_user_message"


def test_session_chat_can_resume_new_topic_after_clarification_confirmation(
    client: TestClient,
) -> None:
    client.post(
        "/api/v1/knowledge-bases/kb-demo-001/documents/upload",
        files={
            "file": (
                "员工制度说明.md",
                (
                    "员工请假需要提前一天提交申请。\n"
                    "团建预算需要先提交活动方案，再走部门审批。"
                ).encode("utf-8"),
                "text/markdown",
            )
        },
    )

    session_response = client.post(
        "/api/v1/sessions",
        json={
            "assistant_id": "asst-demo-001",
            "title": "澄清切换恢复测试",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "员工请假需要做什么？",
            "top_k": 3,
        },
    )

    _, second_chat_data = stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "团建预算怎么申请？",
            "top_k": 3,
        },
    )
    assert second_chat_data["fallback_reason"] == "intent_clarification_required"

    _, third_chat_data = stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "是的",
            "top_k": 3,
        },
    )
    assert third_chat_data["fallback_reason"] is None
    assert "团建预算" in third_chat_data["answer"]
    assert third_chat_data["workflow_trace"][4]["node"] == "clarification_router"
    assert third_chat_data["workflow_trace"][5]["node"] == "clarification_confirm_switch"
    assert "待确认问题“团建预算怎么申请？”继续执行" in third_chat_data[
        "workflow_trace"
    ][5]["detail"]

    session_detail_response = client.get(f"/api/v1/sessions/{session_id}")
    assert session_detail_response.status_code == 200
    session_detail = session_detail_response.json()
    assert session_detail["status"] == "active"
    assert session_detail["workflow_runtime"]["runtime_reason"] is None
    assert (
        session_detail["workflow_runtime"]["resolved_question"]
        == "团建预算怎么申请？"
    )
    assert session_detail["workflow_runtime"]["resume_strategy"] == "none"
    assert session_detail["workflow_runtime"]["latest_node"] == "compose_answer"


def test_session_chat_keeps_waiting_for_specific_follow_up_after_rejecting_switch(
    client: TestClient,
) -> None:
    client.post(
        "/api/v1/knowledge-bases/kb-demo-001/documents/upload",
        files={
            "file": (
                "员工制度说明.md",
                "员工请假需要提前一天提交申请，紧急情况可补交说明。".encode("utf-8"),
                "text/markdown",
            )
        },
    )

    session_response = client.post(
        "/api/v1/sessions",
        json={
            "assistant_id": "asst-demo-001",
            "title": "澄清拒绝切换测试",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "员工请假需要做什么？",
            "top_k": 3,
        },
    )

    _, second_chat_data = stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "团建预算怎么申请？",
            "top_k": 3,
        },
    )
    assert second_chat_data["fallback_reason"] == "intent_clarification_required"

    _, third_chat_data = stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "不是，不切换。",
            "top_k": 3,
        },
    )
    assert third_chat_data["fallback_reason"] == "intent_clarification_required"
    assert "不想切换主题" in third_chat_data["answer"]
    assert third_chat_data["retrieval_count"] == 0
    assert third_chat_data["citations"] == []

    session_detail_response = client.get(f"/api/v1/sessions/{session_id}")
    assert session_detail_response.status_code == 200
    session_detail = session_detail_response.json()
    assert session_detail["status"] == "awaiting_clarification"
    assert (
        "等待用户补充明确追问"
        in session_detail["workflow_runtime"]["runtime_reason"]
    )
    assert (
        session_detail["workflow_runtime"]["clarification_type"]
        == "continue_current_topic"
    )
    assert (
        session_detail["workflow_runtime"]["clarification_stage"]
        == "collect_current_topic_question"
    )
    assert (
        session_detail["workflow_runtime"]["clarification_expected_input"]
        == "follow_up_question"
    )
    assert (
        session_detail["workflow_runtime"]["current_goal"]
        == "员工请假需要做什么？"
    )
    assert session_detail["workflow_runtime"]["pending_question"] is None
    assert (
        session_detail["workflow_runtime"]["runtime_state"]
        == "waiting_clarification_question"
    )
    assert session_detail["workflow_runtime"]["waiting_for"] == "follow_up_question"
    assert session_detail["workflow_runtime"]["resume_strategy"] == "new_user_message"


def test_session_chat_stream_and_messages(client: TestClient) -> None:
    client.post(
        "/api/v1/knowledge-bases/kb-demo-001/documents/upload",
        files={
            "file": (
                "考勤制度.md",
                "员工迟到三次后需要进行提醒谈话，并记录在月度考勤中。".encode("utf-8"),
                "text/markdown",
            )
        },
    )

    session_response = client.post(
        "/api/v1/sessions",
        json={
            "assistant_id": "asst-demo-001",
            "title": "流式聊天测试",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/chat/stream",
        json={
            "question": "迟到三次后会怎么样？",
            "top_k": 3,
        },
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: start" in body
    assert "event: chunk" in body
    assert "event: completed" in body
    assert "迟到三次" in body
    assert "workflow_trace" in body
    assert "selected_kb_ids" in body

    messages_response = client.get(f"/api/v1/sessions/{session_id}/messages")
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


def test_session_chat_stream_uses_model_chunks_when_available(
    client: TestClient,
    monkeypatch,
) -> None:
    from app.services.answer_generation import AnswerGenerationChunk, GeneratedAnswer

    def fake_stream_answer(self, **kwargs):
        yield AnswerGenerationChunk(
            delta="员工迟到三次后，",
            model_name="mock-gpt",
            backend_name="mock-backend",
        )
        yield AnswerGenerationChunk(
            delta="需要进行提醒谈话。",
            model_name="mock-gpt",
            backend_name="mock-backend",
        )
        return GeneratedAnswer(
            content="员工迟到三次后，需要进行提醒谈话。",
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=1,
        )

    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.stream_answer",
        fake_stream_answer,
    )

    client.post(
        "/api/v1/knowledge-bases/kb-demo-001/documents/upload",
        files={
            "file": (
                "考勤制度.md",
                "员工迟到三次后需要进行提醒谈话，并记录在月度考勤中。".encode("utf-8"),
                "text/markdown",
            )
        },
    )

    session_response = client.post(
        "/api/v1/sessions",
        json={
            "assistant_id": "asst-demo-001",
            "title": "模型流式聊天测试",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/chat/stream",
        json={
            "question": "迟到三次后会怎么样？",
            "top_k": 3,
        },
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert 'event: chunk\ndata: {"delta": "员工迟到三次后，"}' in body
    assert 'event: chunk\ndata: {"delta": "需要进行提醒谈话。"}' in body
    assert "mock-gpt" in body
    assert "mock-backend" in body

    messages_response = client.get(f"/api/v1/sessions/{session_id}/messages")
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert messages[1]["content"] == "员工迟到三次后，需要进行提醒谈话。"


def test_session_chat_stream_interrupts_when_review_is_required(
    client: TestClient,
    monkeypatch,
) -> None:
    def should_not_stream(self, **kwargs):
        raise AssertionError("命中 review gate 后不应继续调用流式模型生成。")

    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.stream_answer",
        should_not_stream,
    )

    assistant_response = client.post(
        "/api/v1/assistants",
        json={
            "assistant_name": "法务审核助理",
            "description": "开启 review gate 的测试助理。",
            "system_prompt": "请优先用中文回答。",
            "default_model": "gpt-4o",
            "default_kb_ids": ["kb-demo-001"],
            "tool_keys": [],
            "review_rules": default_review_rules(),
            "review_enabled": True,
        },
    )
    assert assistant_response.status_code == 201
    assistant_id = assistant_response.json()["assistant_id"]

    client.post(
        "/api/v1/knowledge-bases/kb-demo-001/documents/upload",
        files={
            "file": (
                "法务流程.md",
                "涉及起诉、仲裁等事项时，应先提交法务审核并整理证据材料。".encode(
                    "utf-8"
                ),
                "text/markdown",
            )
        },
    )

    session_response = client.post(
        "/api/v1/sessions",
        json={
            "assistant_id": assistant_id,
            "title": "review gate 流式测试",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/chat/stream",
        json={
            "question": "如果我要起诉供应商，应该怎么做？",
            "top_k": 3,
        },
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: start" in body
    assert "event: completed" in body
    assert "review_required" in body
    assert "review_id" in body
    assert "pending" in body
    assert "人工复核规则" in body

    session_detail_response = client.get(f"/api/v1/sessions/{session_id}")
    assert session_detail_response.status_code == 200
    assert session_detail_response.json()["status"] == "awaiting_review"


def test_session_chat_sync_route_is_removed(client: TestClient) -> None:
    session_response = client.post(
        "/api/v1/sessions",
        json={
            "assistant_id": "asst-demo-001",
            "title": "同步路由移除测试",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    chat_response = client.post(
        f"/api/v1/sessions/{session_id}/chat",
        json={
            "question": "员工请假需要做什么？",
            "top_k": 3,
        },
    )
    assert chat_response.status_code == 404


def test_session_chat_stream_emits_error_when_model_is_unavailable(
    client: TestClient,
    monkeypatch,
) -> None:
    def raise_unavailable(self, **kwargs):
        raise AnswerGenerationUnavailableError("未配置 API key。")

    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.stream_answer",
        raise_unavailable,
    )

    client.post(
        "/api/v1/knowledge-bases/kb-demo-001/documents/upload",
        files={
            "file": (
                "考勤制度.md",
                "员工迟到三次后需要进行提醒谈话。".encode("utf-8"),
                "text/markdown",
            )
        },
    )

    session_response = client.post(
        "/api/v1/sessions",
        json={
            "assistant_id": "asst-demo-001",
            "title": "流式模型不可用测试",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/chat/stream",
        json={
            "question": "迟到三次后会怎么样？",
            "top_k": 3,
        },
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: start" in body
    assert "event: error" in body
    assert "当前未配置可用的聊天模型" in body
    assert "event: completed" not in body


def test_session_chat_requests_clarification_when_topic_drift_is_detected(
    client: TestClient,
) -> None:
    client.post(
        "/api/v1/knowledge-bases/kb-demo-001/documents/upload",
        files={
            "file": (
                "员工制度说明.md",
                "员工请假需要提前一天提交申请，紧急情况可补交说明。".encode("utf-8"),
                "text/markdown",
            )
        },
    )

    session_response = client.post(
        "/api/v1/sessions",
        json={
            "assistant_id": "asst-demo-001",
            "title": "意图漂移测试",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "员工请假需要做什么？",
            "top_k": 3,
        },
    )

    _, chat_data = stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "团建预算怎么申请？",
            "top_k": 3,
        },
    )
    assert chat_data["fallback_reason"] == "intent_clarification_required"
    assert chat_data["retrieval_count"] == 0
    assert chat_data["citations"] == []
    assert "偏离本次会话主线" in chat_data["answer"]
    assert chat_data["workflow_trace"][4]["node"] == "clarification_router"
    assert chat_data["workflow_trace"][5]["node"] == "intent_guard"
    assert chat_data["workflow_trace"][6]["node"] == "compose_answer"

    messages_response = client.get(f"/api/v1/sessions/{session_id}/messages")
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert len(messages) == 4
    assert messages[-1]["role"] == "assistant"
    assert "偏离本次会话主线" in messages[-1]["content"]

    session_detail_response = client.get(f"/api/v1/sessions/{session_id}")
    assert session_detail_response.status_code == 200
    assert session_detail_response.json()["status"] == "awaiting_clarification"


def test_session_chat_requests_clarification_for_same_template_different_topic(
    client: TestClient,
) -> None:
    client.post(
        "/api/v1/knowledge-bases/kb-demo-001/documents/upload",
        files={
            "file": (
                "员工制度说明.md",
                (
                    "员工请假需要提交请假单。\n"
                    "员工报销需要提供发票和审批单。"
                ).encode("utf-8"),
                "text/markdown",
            )
        },
    )

    session_response = client.post(
        "/api/v1/sessions",
        json={
            "assistant_id": "asst-demo-001",
            "title": "同句式意图漂移测试",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "员工请假需要什么材料？",
            "top_k": 3,
        },
    )

    _, chat_data = stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "员工报销需要什么材料？",
            "top_k": 3,
        },
    )
    assert chat_data["fallback_reason"] == "intent_clarification_required"
    assert chat_data["retrieval_count"] == 0
    assert chat_data["citations"] == []
    assert "相似问句模板" in chat_data["answer"]
    assert "主题核心分别为“请假”与“报销”" in chat_data["workflow_trace"][5]["detail"]

    session_detail_response = client.get(f"/api/v1/sessions/{session_id}")
    assert session_detail_response.status_code == 200
    session_detail = session_detail_response.json()
    assert session_detail["status"] == "awaiting_clarification"
    assert (
        session_detail["workflow_runtime"]["pending_question"]
        == "员工报销需要什么材料？"
    )


def test_session_chat_can_resume_contextual_follow_up_after_continue_current_topic(
    client: TestClient,
) -> None:
    client.post(
        "/api/v1/knowledge-bases/kb-demo-001/documents/upload",
        files={
            "file": (
                "员工制度说明.md",
                (
                    "员工请假通常需要至少提前一天发起申请。\n"
                    "团建预算需要先提交活动方案，再走部门审批。"
                ).encode("utf-8"),
                "text/markdown",
            )
        },
    )

    session_response = client.post(
        "/api/v1/sessions",
        json={
            "assistant_id": "asst-demo-001",
            "title": "澄清上下文追问恢复测试",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "员工请假需要做什么？",
            "top_k": 3,
        },
    )

    _, second_chat_data = stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "团建预算怎么申请？",
            "top_k": 3,
        },
    )
    assert second_chat_data["fallback_reason"] == "intent_clarification_required"

    _, third_chat_data = stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "不是，不切换。",
            "top_k": 3,
        },
    )
    assert third_chat_data["fallback_reason"] == "intent_clarification_required"

    _, chat_data = stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "继续当前话题：那最晚什么时候提？",
            "top_k": 3,
        },
    )
    assert chat_data["fallback_reason"] is None
    assert "提前一天" in chat_data["answer"]
    assert "已提取具体问题“那最晚什么时候提？”" in chat_data["workflow_trace"][2]["detail"]
    assert "检索问题已改写为：上一轮问题：员工请假需要做什么？" in chat_data[
        "workflow_trace"
    ][3]["detail"]

    session_detail_response = client.get(f"/api/v1/sessions/{session_id}")
    assert session_detail_response.status_code == 200
    session_detail = session_detail_response.json()
    assert session_detail["status"] == "active"
    assert (
        session_detail["workflow_runtime"]["resolved_question"]
        == "那最晚什么时候提？"
    )
