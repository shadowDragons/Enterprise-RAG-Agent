from fastapi.testclient import TestClient

from app.core.review_rules import default_review_rules
from tests.helpers import stream_chat_and_collect_completed


def test_list_assistants(client: TestClient) -> None:
    response = client.get("/api/v1/assistants")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_create_assistant(client: TestClient) -> None:
    custom_review_rules = default_review_rules()[:1]
    response = client.post(
        "/api/v1/assistants",
        json={
            "assistant_name": "测试助理",
            "description": "测试创建的助理。",
            "system_prompt": "请尽量用中文帮助用户。",
            "default_model": "gpt-4o",
            "default_kb_ids": [],
            "tool_keys": [],
            "review_rules": custom_review_rules,
            "review_enabled": True,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["assistant_name"] == "测试助理"
    assert data["review_enabled"] is True
    assert data["review_rule_count"] == 1
    assert data["review_rules"][0]["rule_id"] == custom_review_rules[0]["rule_id"]
    assert data["version"] == 1

    version_response = client.get(f"/api/v1/assistants/{data['assistant_id']}/versions")
    assert version_response.status_code == 200
    versions = version_response.json()
    assert len(versions) == 1
    assert versions[0]["version"] == 1
    assert versions[0]["snapshot"]["assistant_name"] == "测试助理"


def test_update_assistant_creates_new_version_snapshot(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/assistants",
        json={
            "assistant_name": "版本化助理",
            "description": "初始版本。",
            "system_prompt": "请用中文回答。",
            "default_model": "gpt-4o",
            "default_kb_ids": ["kb-demo-001"],
            "tool_keys": [],
            "review_rules": default_review_rules(),
            "review_enabled": False,
        },
    )
    assert create_response.status_code == 201
    assistant_id = create_response.json()["assistant_id"]

    knowledge_base_response = client.post(
        "/api/v1/knowledge-bases",
        json={
            "knowledge_base_name": "合同知识库",
            "description": "合同与法务资料。",
            "default_retrieval_top_k": 6,
        },
    )
    assert knowledge_base_response.status_code == 201
    knowledge_base_id = knowledge_base_response.json()["knowledge_base_id"]

    update_response = client.put(
        f"/api/v1/assistants/{assistant_id}",
        json={
            "assistant_name": "版本化助理 V2",
            "description": "升级后的配置。",
            "system_prompt": "请严格依据知识库回答。",
            "default_model": "gpt-4.1",
            "default_kb_ids": ["kb-demo-001", knowledge_base_id],
            "tool_keys": ["web_search"],
            "review_rules": default_review_rules()[:1],
            "review_enabled": True,
            "change_note": "切换到新版配置",
        },
    )
    assert update_response.status_code == 200
    data = update_response.json()
    assert data["assistant_name"] == "版本化助理 V2"
    assert data["default_model"] == "gpt-4.1"
    assert data["default_kb_count"] == 2
    assert data["version"] == 2
    
    versions_response = client.get(f"/api/v1/assistants/{assistant_id}/versions")
    assert versions_response.status_code == 200
    versions = versions_response.json()
    assert [item["version"] for item in versions[:2]] == [2, 1]
    assert versions[0]["change_note"] == "切换到新版配置"
    assert versions[1]["snapshot"]["assistant_name"] == "版本化助理"

    detail_response = client.get(f"/api/v1/assistants/{assistant_id}/versions/1")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["snapshot"]["assistant_name"] == "版本化助理"
    assert detail["snapshot"]["default_model"] == "gpt-4o"


def test_restore_assistant_version_creates_new_current_version(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/assistants",
        json={
            "assistant_name": "回滚助理",
            "description": "初始配置。",
            "system_prompt": "请用中文回答。",
            "default_model": "gpt-4o",
            "default_kb_ids": ["kb-demo-001"],
            "tool_keys": [],
            "review_rules": default_review_rules(),
            "review_enabled": False,
        },
    )
    assert create_response.status_code == 201
    assistant_id = create_response.json()["assistant_id"]

    update_response = client.put(
        f"/api/v1/assistants/{assistant_id}",
        json={
            "assistant_name": "回滚助理 V2",
            "description": "已切到新配置。",
            "system_prompt": "请严格回答。",
            "default_model": "gpt-4.1",
            "default_kb_ids": ["kb-demo-001"],
            "tool_keys": ["kb_lookup"],
            "review_rules": default_review_rules()[:1],
            "review_enabled": True,
            "change_note": "升级版本二",
        },
    )
    assert update_response.status_code == 200

    restore_response = client.post(
        f"/api/v1/assistants/{assistant_id}/versions/1/restore",
        json={"change_note": "回滚到初始版本"},
    )
    assert restore_response.status_code == 200
    data = restore_response.json()
    assert data["assistant_name"] == "回滚助理"
    assert data["default_model"] == "gpt-4o"
    assert data["review_enabled"] is False
        assert data["version"] == 3

    versions_response = client.get(f"/api/v1/assistants/{assistant_id}/versions")
    assert versions_response.status_code == 200
    versions = versions_response.json()
    assert [item["version"] for item in versions[:3]] == [3, 2, 1]
    assert versions[0]["change_note"] == "回滚到初始版本"


def test_create_assistant_rejects_missing_default_knowledge_base(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/assistants",
        json={
            "assistant_name": "非法助理",
            "description": "引用了不存在的知识库。",
            "system_prompt": "请用中文回答。",
            "default_model": "gpt-4o",
            "default_kb_ids": ["kb-not-found"],
            "tool_keys": [],
            "review_rules": default_review_rules(),
            "review_enabled": False,
        },
    )
    assert response.status_code == 404
    assert "知识库不存在" in response.json()["detail"]


def test_create_assistant_rejects_default_model_outside_allowlist(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/assistants",
        json={
            "assistant_name": "非法模型助理",
            "description": "使用了未允许的默认模型。",
            "system_prompt": "请用中文回答。",
            "default_model": "unsupported-model-x",
            "default_kb_ids": [],
            "tool_keys": [],
            "review_rules": default_review_rules(),
            "review_enabled": False,
        },
    )
    assert response.status_code == 422
    assert "默认模型不在允许列表中" in response.json()["detail"]


def test_delete_assistant_cascades_sessions_reviews_and_audit_logs(
    client: TestClient,
) -> None:
    assistant_response = client.post(
        "/api/v1/assistants",
        json={
            "assistant_name": "待删除助理",
            "description": "测试删除能力。",
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
                "法务资料.md",
                "涉及起诉、仲裁等事项时，应先提交法务审核。".encode("utf-8"),
                "text/markdown",
            )
        },
    )

    session_response = client.post(
        "/api/v1/sessions",
        json={
            "assistant_id": assistant_id,
            "title": "待删除会话",
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

    delete_response = client.delete(f"/api/v1/assistants/{assistant_id}")
    assert delete_response.status_code == 200
    delete_data = delete_response.json()
    assert delete_data["assistant_id"] == assistant_id
    assert delete_data["deleted_session_count"] == 1
    assert delete_data["deleted_review_count"] == 1
    assert delete_data["deleted_audit_log_count"] >= 1

    assistant_detail_response = client.get(f"/api/v1/assistants/{assistant_id}")
    assert assistant_detail_response.status_code == 404

    session_detail_response = client.get(f"/api/v1/sessions/{session_id}")
    assert session_detail_response.status_code == 404

    review_logs_response = client.get(f"/api/v1/reviews/{review_id}/audit-logs")
    assert review_logs_response.status_code == 404
