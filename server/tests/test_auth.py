import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def auth_enabled(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    get_settings.cache_clear()
    try:
        yield
    finally:
        monkeypatch.setenv("AUTH_ENABLED", "false")
        get_settings.cache_clear()


def test_login_and_me(auth_enabled) -> None:
    with TestClient(app) as client:
        token = _login(client, "admin", "admin123456")
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["username"] == "admin"
    assert payload["roles"] == ["admin"]
    assert "assistant:write" in payload["permissions"]


def test_protected_route_requires_token(auth_enabled) -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/assistants")

    assert response.status_code == 401
    assert response.json()["detail"] == "未登录或 token 缺失。"


def test_viewer_cannot_create_assistant_but_admin_can(auth_enabled) -> None:
    payload = {
        "assistant_name": "权限回归助理",
        "description": "用于鉴权回归测试。",
        "system_prompt": "请用中文回答。",
        "default_model": "gpt-4o-mini",
        "default_kb_ids": ["kb-demo-001"],
        "tool_keys": [],
        "review_rules": [],
        "review_enabled": False,
    }

    with TestClient(app) as client:
        viewer_token = _login(client, "viewer", "viewer123456")
        viewer_response = client.post(
            "/api/v1/assistants",
            json=payload,
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        admin_token = _login(client, "admin", "admin123456")
        admin_response = client.post(
            "/api/v1/assistants",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert viewer_response.status_code == 403
    assert "assistant:write" in viewer_response.json()["detail"]
    assert admin_response.status_code == 201
    assert admin_response.json()["assistant_name"] == payload["assistant_name"]
