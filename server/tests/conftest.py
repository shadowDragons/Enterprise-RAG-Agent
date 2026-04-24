import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.services.answer_generation import (
    AnswerGenerationChunk,
    GeneratedAnswer,
)


_TEST_ROOT = Path(tempfile.mkdtemp(prefix="agent-demo-tests-"))
_TEST_STORAGE_ROOT = _TEST_ROOT / "storage"
_TEST_QDRANT_ROOT = _TEST_ROOT / "qdrant"
_TEST_DB_PATH = _TEST_ROOT / "test.db"

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ["STORAGE_ROOT"] = str(_TEST_STORAGE_ROOT)
os.environ["QDRANT_PATH"] = str(_TEST_QDRANT_ROOT)
os.environ["QDRANT_COLLECTION_NAME"] = "document_chunks_test"
os.environ["EMBEDDING_PROVIDER"] = "local"
os.environ["LLM_PROVIDER"] = "local"
os.environ["AUTH_ENABLED"] = "false"

get_settings.cache_clear()

from app.main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _build_mock_answer(question: str, citations) -> str:
    if citations:
        excerpt = citations[0].content.replace("\n", " ").strip()
        if len(excerpt) > 120:
            excerpt = f"{excerpt[:120]}..."
        return f"根据知识库内容，关于“{question}”：{excerpt}"
    return f"根据当前上下文，关于“{question}”的回答。"


@pytest.fixture(autouse=True)
def mock_answer_generation(monkeypatch):
    def fake_generate_answer(self, **kwargs):
        citations = kwargs.get("citations", [])
        answer = _build_mock_answer(kwargs["question"], citations)
        return GeneratedAnswer(
            content=answer,
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=min(len(citations), 6),
        )

    def fake_stream_answer(self, **kwargs):
        citations = kwargs.get("citations", [])
        answer = _build_mock_answer(kwargs["question"], citations)
        yield AnswerGenerationChunk(
            delta=answer,
            model_name="mock-gpt",
            backend_name="mock-backend",
        )
        return GeneratedAnswer(
            content=answer,
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=min(len(citations), 6),
        )

    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        fake_generate_answer,
    )
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.stream_answer",
        fake_stream_answer,
    )
