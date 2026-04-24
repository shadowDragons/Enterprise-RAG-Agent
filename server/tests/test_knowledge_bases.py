from fastapi.testclient import TestClient


def test_list_knowledge_bases(client: TestClient) -> None:
    response = client.get("/api/v1/knowledge-bases")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_create_knowledge_base(client: TestClient) -> None:
    response = client.post(
        "/api/v1/knowledge-bases",
        json={
            "knowledge_base_name": "制度知识库",
            "description": "制度类测试知识库。",
            "default_retrieval_top_k": 6,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["knowledge_base_name"] == "制度知识库"
    assert data["default_retrieval_top_k"] == 6
    assert data["assistant_binding_count"] == 0


def test_update_and_delete_knowledge_base_updates_assistant_binding(
    client: TestClient,
) -> None:
    knowledge_base_response = client.post(
        "/api/v1/knowledge-bases",
        json={
            "knowledge_base_name": "合同知识库",
            "description": "合同资料。",
            "default_retrieval_top_k": 5,
        },
    )
    assert knowledge_base_response.status_code == 201
    knowledge_base_id = knowledge_base_response.json()["knowledge_base_id"]

    assistant_response = client.post(
        "/api/v1/assistants",
        json={
            "assistant_name": "合同助理",
            "description": "绑定新知识库。",
            "system_prompt": "请用中文回答。",
            "default_model": "gpt-4o",
            "default_kb_ids": [knowledge_base_id],
            "tool_keys": [],
            "review_rules": [],
            "review_enabled": False,
        },
    )
    assert assistant_response.status_code == 201
    assistant_id = assistant_response.json()["assistant_id"]

    update_response = client.put(
        f"/api/v1/knowledge-bases/{knowledge_base_id}",
        json={
            "knowledge_base_name": "合同知识库 V2",
            "description": "更新后的合同资料。",
            "default_retrieval_top_k": 8,
        },
    )
    assert update_response.status_code == 200
    update_data = update_response.json()
    assert update_data["knowledge_base_name"] == "合同知识库 V2"
    assert update_data["assistant_binding_count"] == 1

    delete_response = client.delete(f"/api/v1/knowledge-bases/{knowledge_base_id}")
    assert delete_response.status_code == 200
    delete_data = delete_response.json()
    assert delete_data["knowledge_base_id"] == knowledge_base_id
    assert delete_data["unbound_assistant_count"] == 1

    assistant_detail_response = client.get(f"/api/v1/assistants/{assistant_id}")
    assert assistant_detail_response.status_code == 200
    assistant_data = assistant_detail_response.json()
    assert assistant_data["default_kb_ids"] == []
    assert assistant_data["version"] == 2

    knowledge_base_detail_response = client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}"
    )
    assert knowledge_base_detail_response.status_code == 404
