import json

from fastapi.testclient import TestClient


def parse_sse_events(body: str) -> list[tuple[str, dict]]:
    normalized_body = body.replace("\r\n", "\n")
    events: list[tuple[str, dict]] = []

    for block in normalized_body.split("\n\n"):
        stripped = block.strip()
        if not stripped:
            continue

        event = "message"
        data_lines: list[str] = []
        for line in stripped.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())

        if not data_lines:
            continue

        events.append((event, json.loads("\n".join(data_lines))))

    return events


def stream_chat_and_collect(
    client: TestClient,
    session_id: str,
    payload: dict,
) -> tuple[str, list[tuple[str, dict]]]:
    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/chat/stream",
        json=payload,
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    return body, parse_sse_events(body)


def stream_chat_and_collect_completed(
    client: TestClient,
    session_id: str,
    payload: dict,
) -> tuple[str, dict]:
    body, events = stream_chat_and_collect(client, session_id, payload)
    error_payload = next((item for event, item in events if event == "error"), None)
    assert error_payload is None, body

    completed_payload = next(
        (item for event, item in events if event == "completed"),
        None,
    )
    assert completed_payload is not None, body
    return body, completed_payload
