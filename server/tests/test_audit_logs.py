from fastapi.testclient import TestClient

from app.core.review_rules import default_review_rules
from app.services.answer_generation import GeneratedAnswer
from tests.helpers import stream_chat_and_collect_completed


def _create_session(client: TestClient, title: str) -> str:
    response = client.post(
        "/api/v1/sessions",
        json={
            "assistant_id": "asst-demo-001",
            "title": title,
        },
    )
    assert response.status_code == 201
    return response.json()["session_id"]


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
            "title": "review audit 测试",
        },
    )
    assert session_response.status_code == 201
    return assistant_id, session_response.json()["session_id"]


def test_session_audit_logs_cover_completed_and_clarification_turns(
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
    session_id = _create_session(client, "审计日志测试")

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

    audit_response = client.get(f"/api/v1/sessions/{session_id}/audit-logs")
    assert audit_response.status_code == 200
    audit_logs = audit_response.json()
    assert [item["event_type"] for item in audit_logs[:2]] == [
        "clarification_required",
        "chat_completed",
    ]
    assert audit_logs[0]["event_level"] == "warning"
    assert (
        audit_logs[0]["detail_payload"]["clarification_stage"] == "confirm_switch"
    )
    assert audit_logs[1]["detail_payload"]["resolved_question"] == "员工请假需要做什么？"


def test_review_audit_logs_cover_pending_approve_and_failure(
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

    pending_logs_response = client.get(f"/api/v1/reviews/{review_id}/audit-logs")
    assert pending_logs_response.status_code == 200
    pending_logs = pending_logs_response.json()
    assert pending_logs[0]["event_type"] == "review_pending"
    assert pending_logs[0]["event_level"] == "warning"

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
        json={"reviewer_note": "可以继续自动生成。"},
    )
    assert approve_response.status_code == 200

    approved_logs_response = client.get(f"/api/v1/reviews/{review_id}/audit-logs")
    assert approved_logs_response.status_code == 200
    approved_logs = approved_logs_response.json()
    assert [item["event_type"] for item in approved_logs[:2]] == [
        "review_approved",
        "review_pending",
    ]
    assert approved_logs[0]["detail_payload"]["review_status"] == "approved"

    failed_approve_response = client.post(
        f"/api/v1/reviews/{review_id}/approve",
        json={"reviewer_note": "重复提交。"},
    )
    assert failed_approve_response.status_code == 409

    failed_logs_response = client.get(
        f"/api/v1/reviews/{review_id}/audit-logs",
        params={"event_type": "review_resume_failed"},
    )
    assert failed_logs_response.status_code == 200
    failed_logs = failed_logs_response.json()
    assert len(failed_logs) == 1
    assert failed_logs[0]["event_level"] == "error"
    assert "不能重复提交审核结论" in failed_logs[0]["summary"]
