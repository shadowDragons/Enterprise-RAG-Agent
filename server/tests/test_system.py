from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models import Document, Job, Message, ReviewTask, Session


def test_system_overview_exposes_alerts(client: TestClient) -> None:
    now = datetime.now(timezone.utc)
    session_id = str(uuid4())
    message_id = str(uuid4())

    with SessionLocal() as db:
        db.add(
            Session(
                session_id=session_id,
                assistant_id="asst-demo-001",
                title="系统总览测试会话",
                status="awaiting_review",
                runtime_state="waiting_review_escalated",
                runtime_label="人工审核已超时，等待升级处理",
                runtime_waiting_for="escalated_human_review",
                runtime_resume_strategy="command_resume",
                workflow_thread_id="system-overview-thread",
                runtime_reason="人工审核已超时",
                runtime_current_goal="系统总览测试问题",
                runtime_resolved_question="系统总览测试问题",
                runtime_pending_question="",
                runtime_clarification_type="",
                runtime_clarification_stage="",
                runtime_clarification_expected_input="",
                runtime_clarification_reason="",
                runtime_context={},
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            Message(
                message_id=message_id,
                session_id=session_id,
                role="assistant",
                content="待审核回答",
                citations=[],
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            ReviewTask(
                review_id=str(uuid4()),
                session_id=session_id,
                assistant_id="asst-demo-001",
                pending_message_id=message_id,
                status="escalated",
                escalation_level=1,
                escalation_reason="人工审核超过 SLA，已自动升级。",
                question="系统总览测试问题",
                review_reason="命中审核规则",
                reviewer_note="",
                final_answer="",
                selected_knowledge_base_id="kb-demo-001",
                selected_kb_ids=["kb-demo-001"],
                citations=[],
                retrieval_count=1,
                checkpoint_payload={},
                workflow_trace=[],
                escalated_at=now,
                reviewed_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            Job(
                job_id=str(uuid4()),
                job_type="document_ingestion",
                target_id="doc-system-overview",
                status="failed",
                progress=0.35,
                error_message="模拟任务失败",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

    response = client.get("/api/v1/system/overview")
    assert response.status_code == 200
    payload = response.json()

    assert payload["health_status"] == "critical"
    assert payload["runtime"]["auth_enabled"] is False
    assert payload["resources"]["assistants_total"] >= 1
    assert payload["tasks"]["jobs_failed"] >= 1
    assert payload["tasks"]["reviews_escalated"] >= 1
    assert payload["runtime"]["llm_model"]
    assert payload["runtime"]["embedding_model"]
    assert payload["readiness"]["overall_status"] in {"warning", "failed"}
    assert (
        payload["readiness"]["failed"] + payload["readiness"]["warnings"]
    ) >= 1
    alert_codes = {item["code"] for item in payload["alerts"]}
    assert "jobs_failed" in alert_codes
    assert "reviews_escalated" in alert_codes


def test_system_maintenance_can_reconcile_reviews_and_retry_failed_jobs(
    client: TestClient,
) -> None:
    now = datetime.now(timezone.utc)
    session_id = str(uuid4())
    message_id = str(uuid4())

    upload_response = client.post(
        "/api/v1/knowledge-bases/kb-demo-001/documents/upload",
        files={
            "file": (
                "系统维护失败文档.md",
                "   \n\t".encode("utf-8"),
                "text/markdown",
            )
        },
    )
    assert upload_response.status_code == 201
    job_id = upload_response.json()["job"]["job_id"]
    document_id = upload_response.json()["document"]["document_id"]

    with SessionLocal() as db:
        document = db.get(Document, document_id)
        assert document is not None
        with open(document.file_path, "w", encoding="utf-8") as handle:
            handle.write("# 系统维护修复后文档\n\n现在有可解析的文本内容。")

        stale_time = datetime.now(timezone.utc) - timedelta(minutes=40)
        db.add(
            Session(
                session_id=session_id,
                assistant_id="asst-demo-001",
                title="系统维护会话",
                status="awaiting_review",
                runtime_state="waiting_review",
                runtime_label="等待人工审核",
                runtime_waiting_for="human_review",
                runtime_resume_strategy="command_resume",
                workflow_thread_id="system-maintenance-thread",
                runtime_reason="等待人工审核",
                runtime_current_goal="系统维护测试问题",
                runtime_resolved_question="系统维护测试问题",
                runtime_pending_question="",
                runtime_clarification_type="",
                runtime_clarification_stage="",
                runtime_clarification_expected_input="",
                runtime_clarification_reason="",
                runtime_context={},
                created_at=stale_time,
                updated_at=stale_time,
            )
        )
        db.add(
            Message(
                message_id=message_id,
                session_id=session_id,
                role="assistant",
                content="待审核回答",
                citations=[],
                created_at=stale_time,
                updated_at=stale_time,
            )
        )
        db.add(
            ReviewTask(
                review_id=str(uuid4()),
                session_id=session_id,
                assistant_id="asst-demo-001",
                pending_message_id=message_id,
                status="pending",
                escalation_level=0,
                escalation_reason="",
                question="系统维护测试问题",
                review_reason="命中审核规则",
                reviewer_note="",
                final_answer="",
                selected_knowledge_base_id="kb-demo-001",
                selected_kb_ids=["kb-demo-001"],
                citations=[],
                retrieval_count=1,
                checkpoint_payload={"workflow_thread_id": "system-maintenance-thread"},
                workflow_trace=[],
                escalated_at=None,
                reviewed_at=None,
                created_at=stale_time,
                updated_at=stale_time,
            )
        )
        db.commit()

    response = client.post(
        "/api/v1/system/maintenance/run",
        json={
            "reconcile_overdue_reviews": True,
            "retry_failed_jobs": True,
            "job_retry_limit": 5,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["reconcile_overdue_reviews_count"] >= 1
    assert payload["retried_job_count"] >= 1
    assert job_id in payload["retried_job_ids"]

    job_response = client.get(f"/api/v1/jobs/{job_id}")
    assert job_response.status_code == 200
    assert job_response.json()["status"] == "completed"

    overview_response = client.get("/api/v1/system/overview")
    assert overview_response.status_code == 200
    overview_payload = overview_response.json()
    assert overview_payload["tasks"]["reviews_escalated"] >= 1
