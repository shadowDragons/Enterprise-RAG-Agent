from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.review_rules import default_review_rules
from app.db.session import SessionLocal
from app.repositories.review_tasks import ReviewTaskRepository
from app.services.answer_generation import GeneratedAnswer
from tests.helpers import stream_chat_and_collect_completed


def _create_review_session(client: TestClient) -> tuple[str, str]:
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
            "title": "review task 测试",
        },
    )
    assert session_response.status_code == 201
    return assistant_id, session_response.json()["session_id"]


def test_review_task_is_created_for_review_required_chat(client: TestClient) -> None:
    _, session_id = _create_review_session(client)

    _, chat_data = stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "如果我要起诉供应商，应该怎么做？",
            "top_k": 3,
        },
    )
    assert chat_data["fallback_reason"] == "review_required"
    assert chat_data["review_id"]
    assert chat_data["review_status"] == "pending"

    review_response = client.get("/api/v1/reviews", params={"status": "pending"})
    assert review_response.status_code == 200
    reviews = review_response.json()
    review_item = next(item for item in reviews if item["review_id"] == chat_data["review_id"])
    assert review_item["sla"]["policy_key"] == "human_review"
    assert review_item["sla"]["status"] in {"normal", "warning", "breached"}
    assert review_item["status"] == "pending"
    assert review_item["escalation_reason"] == ""

    messages_response = client.get(f"/api/v1/sessions/{session_id}/messages")
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert len(messages) == 2
    assert "人工复核规则" in messages[1]["content"]

    session_detail_response = client.get(f"/api/v1/sessions/{session_id}")
    assert session_detail_response.status_code == 200
    assert session_detail_response.json()["status"] == "awaiting_review"


def test_review_approve_resumes_generation_and_updates_message(
    client: TestClient,
    monkeypatch,
) -> None:
    _, session_id = _create_review_session(client)
    _, chat_data = stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "如果我要起诉供应商，应该怎么做？",
            "top_k": 3,
        },
    )
    review_id = chat_data["review_id"]

    def fake_generate(self, **kwargs) -> GeneratedAnswer:
        return GeneratedAnswer(
            content="请先整理证据并提交法务审核，再决定是否进入起诉流程。[1]",
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=1,
        )

    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        fake_generate,
    )

    approve_response = client.post(
        f"/api/v1/reviews/{review_id}/approve",
        json={"reviewer_note": "可以继续按知识库内容自动生成。"},
    )
    assert approve_response.status_code == 200
    review_data = approve_response.json()
    assert review_data["status"] == "approved"
    assert "请先整理证据并提交法务审核" in review_data["final_answer"]
    assert review_data["sla"]["status"] == "completed"
    assert review_data["workflow_trace"][-2]["node"] == "review_hold"
    assert review_data["workflow_trace"][-1]["node"] == "compose_answer"

    messages_response = client.get(f"/api/v1/sessions/{session_id}/messages")
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert messages[1]["content"] == review_data["final_answer"]

    session_detail_response = client.get(f"/api/v1/sessions/{session_id}")
    assert session_detail_response.status_code == 200
    session_detail = session_detail_response.json()
    assert session_detail["status"] == "active"
    assert session_detail["workflow_runtime"]["latest_node"] == "compose_answer"
    assert session_detail["workflow_runtime"]["runtime_state"] == (
        "completed_after_review"
    )
    assert session_detail["workflow_runtime"]["resume_strategy"] == "none"
    assert session_detail["workflow_runtime"]["workflow_can_resume"] is False


def test_review_reject_writes_manual_answer(client: TestClient) -> None:
    _, session_id = _create_review_session(client)
    _, chat_data = stream_chat_and_collect_completed(
        client,
        session_id,
        {
            "question": "如果我要起诉供应商，应该怎么做？",
            "top_k": 3,
        },
    )
    review_id = chat_data["review_id"]

    reject_response = client.post(
        f"/api/v1/reviews/{review_id}/reject",
        json={
            "reviewer_note": "此类问题必须由法务人工接管。",
            "manual_answer": "该问题已转法务人工处理，请联系法务同事继续跟进。",
        },
    )
    assert reject_response.status_code == 200
    review_data = reject_response.json()
    assert review_data["status"] == "rejected"
    assert review_data["sla"]["status"] == "completed"
    assert (
        review_data["final_answer"]
        == "该问题已转法务人工处理，请联系法务同事继续跟进。"
    )

    messages_response = client.get(f"/api/v1/sessions/{session_id}/messages")
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert messages[1]["content"] == review_data["final_answer"]

    session_detail_response = client.get(f"/api/v1/sessions/{session_id}")
    assert session_detail_response.status_code == 200
    session_detail = session_detail_response.json()
    assert session_detail["status"] == "active"
    assert session_detail["workflow_runtime"]["latest_node"] == "review_hold"
    assert session_detail["workflow_runtime"]["runtime_state"] == (
        "completed_with_manual_review"
    )
    assert session_detail["workflow_runtime"]["resume_strategy"] == "none"


def test_review_approve_rejects_legacy_task_without_workflow_thread(
    client: TestClient,
) -> None:
    _, session_id = _create_review_session(client)
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
        review_task.checkpoint_payload = {}
        db.add(review_task)
        db.commit()

    approve_response = client.post(
        f"/api/v1/reviews/{review_id}/approve",
        json={"reviewer_note": "尝试恢复。"},
    )
    assert approve_response.status_code == 409
    assert "workflow thread" in approve_response.json()["detail"]


def test_escalated_review_can_still_be_approved(
    client: TestClient,
    monkeypatch,
) -> None:
    _, session_id = _create_review_session(client)
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

    def fake_generate(self, **kwargs) -> GeneratedAnswer:
        return GeneratedAnswer(
            content="请先整理证据并提交法务审核，再决定是否进入起诉流程。[1]",
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=1,
        )

    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        fake_generate,
    )

    approve_response = client.post(
        f"/api/v1/reviews/{review_id}/approve",
        json={"reviewer_note": "超时后仍然允许继续自动生成。"},
    )
    assert approve_response.status_code == 200
    review_data = approve_response.json()
    assert review_data["status"] == "approved"
    assert review_data["sla"]["status"] == "completed"
    assert review_data["escalation_reason"]
    assert review_data["escalated_at"] is not None


def test_list_review_tasks_supports_sla_status_filter(client: TestClient) -> None:
    _, session_id = _create_review_session(client)
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

    review_response = client.get("/api/v1/reviews", params={"sla_status": "breached"})
    assert review_response.status_code == 200
    review_item = next(item for item in review_response.json() if item["review_id"] == review_id)
    assert review_item["status"] == "escalated"
    assert review_item["escalation_level"] >= 1
    assert review_item["escalation_reason"]
    assert review_item["escalated_at"] is not None
    assert review_item["sla"]["status"] == "breached"
    assert review_item["sla"]["breach_seconds"] >= 1
