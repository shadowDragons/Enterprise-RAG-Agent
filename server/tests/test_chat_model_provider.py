from langchain_core.messages import HumanMessage

from app.integrations.chat_model_provider import OpenAICompatibleChatBackend


class _FakeStreamingResponse:
    def __init__(self, lines: list[str]) -> None:
        self._lines = [line.encode("utf-8") for line in lines]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def __iter__(self):
        return iter(self._lines)


def test_openai_compatible_chat_backend_stream_parses_sse_chunks(monkeypatch) -> None:
    backend = OpenAICompatibleChatBackend()

    def fake_urlopen(*args, **kwargs):
        return _FakeStreamingResponse(
            [
                'data: {"model":"mock-gpt","choices":[{"delta":{"content":"你好"},"finish_reason":null}]}',
                "",
                'data: {"model":"mock-gpt","choices":[{"delta":{"content":"，世界"},"finish_reason":null}]}',
                "data: [DONE]",
            ]
        )

    monkeypatch.setattr(
        "app.integrations.chat_model_provider.request.urlopen",
        fake_urlopen,
    )

    chunks = list(
        backend.stream(
            messages=[HumanMessage(content="你好")],
            model="mock-gpt",
            temperature=0.2,
        )
    )

    assert "".join(chunk.delta for chunk in chunks) == "你好，世界"
    assert all(chunk.model_name == "mock-gpt" for chunk in chunks)
