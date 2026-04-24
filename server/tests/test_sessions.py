from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.review_rules import default_review_rules
from app.db.session import SessionLocal
from app.repositories.review_tasks import ReviewTaskRepository
from tests.helpers import stream_chat_and_collect_completed


def test_list_sessions(client: TestClient) -> None:
    response = client.get("/api/v1/sessions")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_create_session(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sessions",
        json={
            "assistant_id": "asst-demo-001",
            "title": "制度问答会话",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["assistant_id"] == "asst-demo-001"
    assert data["assistant_name"] == "通用知识助手"
    assert data["title"] == "制度问答会话"
    assert data["message_count"] == 0
    assert data["workflow_runtime"] is None


def test_session_detail_exposes_pending_review_runtime(client: TestClient) -> None:
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
            "title": "运行态观测测试",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    _, chat_data = stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "如果我要起诉供应商，应该怎么做？",
            "top_k": 3,
        },
    )
    review_id = chat_data["review_id"]

    session_detail_response = client.get(f"/api/v1/sessions/{session_id}")
    assert session_detail_response.status_code == 200
    session_detail = session_detail_response.json()
    assert session_detail["status"] == "awaiting_review"
    assert session_detail["workflow_runtime"]["pending_review_id"] == review_id
    assert "法律" in session_detail["workflow_runtime"]["pending_review_reason"]
    assert "法律" in session_detail["workflow_runtime"]["runtime_reason"]
    assert (
        session_detail["workflow_runtime"]["resolved_question"]
        == "如果我要起诉供应商，应该怎么做？"
    )
    assert session_detail["workflow_runtime"]["runtime_state"] == "waiting_review"
    assert session_detail["workflow_runtime"]["runtime_label"] == "等待人工审核"
    assert session_detail["workflow_runtime"]["waiting_for"] == "human_review"
    assert session_detail["workflow_runtime"]["resume_strategy"] == "command_resume"
    assert session_detail["workflow_runtime"]["latest_node"] == "review_gate"
    assert session_detail["workflow_runtime"]["workflow_thread_id"]
    assert session_detail["workflow_runtime"]["workflow_checkpoint_id"]
    assert session_detail["workflow_runtime"]["workflow_checkpoint_updated_at"]
    assert session_detail["workflow_runtime"]["workflow_source"] == "loop"
    assert session_detail["workflow_runtime"]["workflow_step"] is not None
    assert session_detail["workflow_runtime"]["workflow_checkpoint_backend"] == (
        "database"
    )
    assert "内置数据库" in session_detail["workflow_runtime"][
        "workflow_checkpoint_backend_label"
    ]
    assert session_detail["workflow_runtime"]["checkpoint_status"] == "resumable"
    assert session_detail["workflow_runtime"]["workflow_pending_write_count"] is not None
    assert session_detail["workflow_runtime"]["workflow_can_resume"] is True

    list_response = client.get("/api/v1/sessions")
    assert list_response.status_code == 200
    listed = next(
        item for item in list_response.json() if item["session_id"] == session_id
    )
    assert listed["workflow_runtime"]["pending_review_id"] == review_id
    assert listed["workflow_runtime"]["latest_node"] == "review_gate"
    assert listed["workflow_runtime"]["runtime_state"] == "waiting_review"


def test_delete_session_cascades_messages_reviews_and_audit_logs(
    client: TestClient,
) -> None:
    session_response = client.post(
        "/api/v1/sessions",
        json={
            "assistant_id": "asst-demo-001",
            "title": "待删除会话",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "请总结一下制度知识库的重点。",
            "top_k": 3,
        },
    )

    delete_response = client.delete(f"/api/v1/sessions/{session_id}")
    assert delete_response.status_code == 200
    delete_data = delete_response.json()
    assert delete_data["session_id"] == session_id
    assert delete_data["assistant_id"] == "asst-demo-001"
    assert delete_data["deleted_message_count"] >= 2
    assert delete_data["deleted_audit_log_count"] >= 1

    session_detail_response = client.get(f"/api/v1/sessions/{session_id}")
    assert session_detail_response.status_code == 404

    audit_logs_response = client.get(f"/api/v1/sessions/{session_id}/audit-logs")
    assert audit_logs_response.status_code == 404


def test_session_detail_exposes_escalated_review_runtime(client: TestClient) -> None:
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
            "title": "审核超时观测测试",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    _, chat_data = stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "如果我要起诉供应商，应该怎么做？",
            "top_k": 3,
        },
    )
    review_id = chat_data["review_id"]

    with SessionLocal() as db:
        repository = ReviewTaskRepository(db)
        review_task = repository.get(review_id)
        assert review_task is not None
        stale_time = datetime.now(timezone.utc) - timedelta(hours=2)
        review_task.created_at = stale_time
        review_task.updated_at = stale_time
        db.add(review_task)
        db.commit()

    session_detail_response = client.get(f"/api/v1/sessions/{session_id}")
    assert session_detail_response.status_code == 200
    session_detail = session_detail_response.json()
    assert session_detail["status"] == "awaiting_review"
    assert session_detail["workflow_runtime"]["pending_review_status"] == "escalated"
    assert session_detail["workflow_runtime"]["pending_review_escalation_reason"]
    assert session_detail["workflow_runtime"]["pending_review_escalated_at"] is not None
    assert session_detail["workflow_runtime"]["runtime_state"] == (
        "waiting_review_escalated"
    )
    assert session_detail["workflow_runtime"]["runtime_label"] == (
        "人工审核已超时，等待升级处理"
    )
    assert session_detail["workflow_runtime"]["waiting_for"] == (
        "escalated_human_review"
    )
