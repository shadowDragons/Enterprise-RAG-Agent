import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.core.review_rules import default_review_rules
from app.schemas.chat import ChatCitation
from app.services.answer_generation import (
    AnswerGenerationUnavailableError,
    GeneratedAnswer,
)
from app.services.retrieval import RetrievalService
from app.workflows.chat_graph import build_chat_workflow



def test_chat_workflow_builds_answer_without_citations() -> None:
    workflow = build_chat_workflow(include_compose_answer=True)
    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": [],
            },
            "question": "测试问题",
            "message_history": [],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["retrieval_count"] == 0
    assert result["citations"] == []
    assert "测试问题" in result["answer"]
    assert result["fallback_reason"] == "no_knowledge_base_selected"
    assert result["selected_kb_ids"] == []
    assert [item.node for item in result["workflow_trace"]] == [
        "assistant_config",
        "kb_scope",
        "question_intake",
        "memory_manager",
        "clarification_router",
        "intent_guard",
        "compose_answer",
    ]


def test_chat_workflow_uses_requested_knowledge_base() -> None:
    workflow = build_chat_workflow(include_compose_answer=True)
    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "question": "测试问题",
            "message_history": [],
            "requested_knowledge_base_ids": ["kb-requested-001", "kb-requested-002"],
            "top_k": 3,
        }
    )

    assert result["selected_knowledge_base_id"] == "kb-requested-001"
    assert result["selected_kb_ids"] == ["kb-requested-001", "kb-requested-002"]
    assert [item.node for item in result["workflow_trace"][:6]] == [
        "assistant_config",
        "kb_scope",
        "question_intake",
        "memory_manager",
        "clarification_router",
        "intent_guard",
    ]


def test_chat_workflow_prefers_llm_generation(monkeypatch) -> None:
    def fake_retrieve(
        self, knowledge_base_id: str, query: str, top_k: int
    ) -> list[dict]:
        return [
            ChatCitation(
                chunk_id="chunk-001",
                document_id="doc-001",
                knowledge_base_id=knowledge_base_id,
                chunk_index=0,
                file_name="请假制度.md",
                content="员工请假需要提前一天提交申请。",
                score=0.92,
                vector_score=0.88,
                lexical_score=0.97,
                embedding_backend="local_hash",
            ).model_dump()
        ]

    def fake_generate(self, **kwargs) -> GeneratedAnswer:
        assert kwargs["model_name"] == "gpt-4o-mini"
        return GeneratedAnswer(
            content="员工请假通常需要提前一天提交申请。[1]",
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=1,
        )

    monkeypatch.setattr(RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        fake_generate,
    )
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "question": "员工请假需要做什么？",
            "message_history": [],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["answer"] == "员工请假通常需要提前一天提交申请。[1]"
    assert result["fallback_reason"] is None
    assert result["retrieval_count"] == 1
    assert "mock-gpt" in result["workflow_trace"][-1].detail
    assert "mock-backend" in result["workflow_trace"][-1].detail


def test_chat_workflow_returns_no_hit_answer_without_fallback_reason(
    monkeypatch,
) -> None:
    def fake_retrieve(
        self, knowledge_base_id: str, query: str, top_k: int
    ) -> list[dict]:
        return []

    monkeypatch.setattr(RetrievalService, "retrieve", fake_retrieve)
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "question": "完全无关的问题",
            "message_history": [],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["retrieval_count"] == 0
    assert result["citations"] == []
    assert result["fallback_reason"] is None
    assert "没有在知识库范围 kb-default-001 中检索到" in result["answer"]
    assert result["workflow_trace"][-2].node == "retrieval"
    assert result["workflow_trace"][-1].node == "compose_answer"


def test_chat_workflow_falls_back_when_llm_is_unavailable(monkeypatch) -> None:
    def fake_retrieve(
        self, knowledge_base_id: str, query: str, top_k: int
    ) -> list[dict]:
        return [
            ChatCitation(
                chunk_id="chunk-001",
                document_id="doc-001",
                knowledge_base_id=knowledge_base_id,
                chunk_index=0,
                file_name="报销制度.md",
                content="员工报销需要提供发票和审批单。",
                score=0.89,
                vector_score=0.81,
                lexical_score=0.96,
                embedding_backend="local_hash",
            ).model_dump()
        ]

    def raise_unavailable(self, **kwargs):
        raise AnswerGenerationUnavailableError("未配置 API key。")

    monkeypatch.setattr(RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        raise_unavailable,
    )
    workflow = build_chat_workflow(include_compose_answer=True)

    with pytest.raises(AnswerGenerationUnavailableError, match="未配置 API key"):
        workflow.invoke(
            {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "assistant_config": {
                    "assistant_id": "asst-test-001",
                    "assistant_name": "测试助理",
                    "system_prompt": "请用中文回答。",
                    "default_model": "gpt-4o-mini",
                    "default_kb_ids": ["kb-default-001"],
                },
                "question": "员工报销需要什么材料？",
                "message_history": [],
                "requested_knowledge_base_ids": [],
                "top_k": 3,
            }
        )


def test_chat_workflow_rewrites_follow_up_question_for_retrieval(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_retrieve(
        self,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[dict]:
        captured["query"] = query
        return [
            ChatCitation(
                chunk_id="chunk-001",
                document_id="doc-001",
                knowledge_base_id=knowledge_base_id,
                chunk_index=0,
                file_name="报销制度.md",
                content="员工报销需要提供发票和审批单。",
                score=0.93,
                vector_score=0.86,
                lexical_score=0.97,
                embedding_backend="local_hash",
            ).model_dump()
        ]

    def fake_generate(self, **kwargs) -> GeneratedAnswer:
        assert kwargs["effective_question"].startswith(
            "上一轮问题：员工请假需要做什么？"
        )
        assert "用户：员工请假需要做什么？" in kwargs["memory_summary"]
        return GeneratedAnswer(
            content="员工报销需要提供发票和审批单。[1]",
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=1,
        )

    monkeypatch.setattr(RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        fake_generate,
    )
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "question": "那报销呢？",
            "message_history": [
                {
                    "role": "user",
                    "content": "员工请假需要做什么？",
                },
                {
                    "role": "assistant",
                    "content": "员工请假需要提前一天提交申请。",
                },
            ],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert captured["query"].startswith("上一轮问题：员工请假需要做什么？")
    assert result["workflow_trace"][2].node == "question_intake"
    assert result["workflow_trace"][3].node == "memory_manager"
    assert result["workflow_trace"][5].node == "intent_guard"
    assert "检索问题已改写为" in result["workflow_trace"][3].detail
    assert "连续追问特征" in result["workflow_trace"][5].detail


def test_chat_workflow_interrupts_answer_when_review_is_required(monkeypatch) -> None:
    def fake_retrieve(
        self, knowledge_base_id: str, query: str, top_k: int
    ) -> list[dict]:
        return [
            ChatCitation(
                chunk_id="chunk-legal-001",
                document_id="doc-legal-001",
                knowledge_base_id=knowledge_base_id,
                chunk_index=0,
                file_name="法务流程.md",
                content="涉及起诉、仲裁等事项时，应先提交法务审核并整理证据材料。",
                score=0.95,
                vector_score=0.9,
                lexical_score=0.98,
                embedding_backend="local_hash",
            ).model_dump()
        ]

    def should_not_generate(self, **kwargs):
        raise AssertionError("命中 review gate 后不应继续调用模型生成。")

    monkeypatch.setattr(RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        should_not_generate,
    )
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
                "review_rules": default_review_rules(),
                "review_enabled": True,
            },
            "question": "如果我要起诉供应商，应该怎么做？",
            "message_history": [],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["fallback_reason"] == "review_required"
    assert "人工复核规则" in result["answer"]
    assert [item.node for item in result["workflow_trace"][-2:]] == [
        "review_gate",
        "compose_answer",
    ]
    assert "法律" in result["workflow_trace"][-2].detail
    assert "风险规则" in result["workflow_trace"][-2].detail


def test_chat_workflow_can_interrupt_and_resume_review(monkeypatch) -> None:
    def fake_retrieve(
        self, knowledge_base_id: str, query: str, top_k: int
    ) -> list[dict]:
        return [
            ChatCitation(
                chunk_id="chunk-legal-001",
                document_id="doc-legal-001",
                knowledge_base_id=knowledge_base_id,
                chunk_index=0,
                file_name="法务流程.md",
                content="涉及起诉、仲裁等事项时，应先提交法务审核并整理证据材料。",
                score=0.95,
                vector_score=0.9,
                lexical_score=0.98,
                embedding_backend="local_hash",
            ).model_dump()
        ]

    def fake_generate(self, **kwargs) -> GeneratedAnswer:
        return GeneratedAnswer(
            content="请先整理证据并提交法务审核，再决定是否进入起诉流程。[1]",
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=1,
        )

    monkeypatch.setattr(RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        fake_generate,
    )

    workflow = build_chat_workflow(
        include_compose_answer=True,
        checkpointer=MemorySaver(),
    )
    config = {"configurable": {"thread_id": "review-thread-001"}}
    interrupted = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
                "review_rules": default_review_rules(),
                "review_enabled": True,
            },
            "question": "如果我要起诉供应商，应该怎么做？",
            "message_history": [],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
            "review_interrupt_enabled": True,
        },
        config=config,
    )

    assert interrupted["fallback_reason"] == "review_required"
    assert interrupted["review_reason"].startswith("检测到 法律")
    assert interrupted["__interrupt__"]

    resumed = workflow.invoke(
        Command(resume={"action": "approve", "reviewer_note": "可以继续自动生成。"}),
        config=config,
    )

    assert resumed["answer"] == "请先整理证据并提交法务审核，再决定是否进入起诉流程。[1]"
    assert [item.node for item in resumed["workflow_trace"][-2:]] == [
        "review_hold",
        "compose_answer",
    ]


def test_chat_workflow_reject_uses_resolved_question_after_explicit_switch(
    monkeypatch,
) -> None:
    def fake_retrieve(
        self, knowledge_base_id: str, query: str, top_k: int
    ) -> list[dict]:
        assert query == "基金怎么买？"
        return [
            ChatCitation(
                chunk_id="chunk-finance-001",
                document_id="doc-finance-001",
                knowledge_base_id=knowledge_base_id,
                chunk_index=0,
                file_name="投资须知.md",
                content="购买基金前应充分评估风险承受能力。",
                score=0.95,
                vector_score=0.9,
                lexical_score=0.98,
                embedding_backend="local_hash",
            ).model_dump()
        ]

    def should_not_generate(self, **kwargs):
        raise AssertionError("审核驳回时不应继续调用模型生成。")

    monkeypatch.setattr(RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        should_not_generate,
    )

    workflow = build_chat_workflow(
        include_compose_answer=True,
        checkpointer=MemorySaver(),
    )
    config = {"configurable": {"thread_id": "review-thread-002"}}
    interrupted = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
                "review_rules": default_review_rules(),
                "review_enabled": True,
            },
            "question": "换个问题：基金怎么买？",
            "message_history": [
                {
                    "role": "user",
                    "content": "员工请假需要做什么？",
                },
                {
                    "role": "assistant",
                    "content": "员工请假需要提前一天提交申请。",
                },
            ],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
            "review_interrupt_enabled": True,
        },
        config=config,
    )

    assert interrupted["fallback_reason"] == "review_required"
    assert interrupted["review_reason"].startswith("检测到 投资")
    assert interrupted["__interrupt__"]

    resumed = workflow.invoke(
        Command(
            resume={
                "action": "reject",
                "reviewer_note": "投资问题需人工接管。",
                "manual_answer": "",
            }
        ),
        config=config,
    )

    assert "基金怎么买？" in resumed["answer"]
    assert "换个问题：" not in resumed["answer"]
    assert resumed["fallback_reason"] is None
    assert resumed["workflow_trace"][-1].node == "review_hold"


def test_chat_workflow_requests_clarification_when_topic_drift_is_detected() -> None:
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "question": "团建预算怎么申请？",
            "message_history": [
                {
                    "role": "user",
                    "content": "员工请假需要做什么？",
                },
                {
                    "role": "assistant",
                    "content": "员工请假需要提前一天提交申请。",
                },
            ],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["fallback_reason"] == "intent_clarification_required"
    assert result["retrieval_count"] == 0
    assert result["citations"] == []
    assert result["clarification_stage"] == "confirm_switch"
    assert result["clarification_expected_input"] == "topic_switch_confirmation"
    assert "偏离本次会话主线" in result["answer"]
    assert [item.node for item in result["workflow_trace"][-2:]] == [
        "intent_guard",
        "compose_answer",
    ]
    assert "相似度" in result["workflow_trace"][-2].detail


def test_chat_workflow_waits_for_new_topic_question_after_explicit_switch_without_question(
    monkeypatch,
) -> None:
    def should_not_retrieve(self, knowledge_base_id: str, query: str, top_k: int):
        raise AssertionError("尚未给出新主题具体问题时不应继续检索。")

    def should_not_generate(self, **kwargs):
        raise AssertionError("尚未给出新主题具体问题时不应继续调用模型生成。")

    monkeypatch.setattr(RetrievalService, "retrieve", should_not_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        should_not_generate,
    )
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "question": "换个问题",
            "message_history": [
                {
                    "role": "user",
                    "content": "员工请假需要做什么？",
                },
                {
                    "role": "assistant",
                    "content": "员工请假需要提前一天提交申请。",
                },
            ],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["fallback_reason"] == "intent_clarification_required"
    assert result["retrieval_count"] == 0
    assert result["citations"] == []
    assert result["resolved_question"] == ""
    assert result["clarification_type"] == "new_topic_question"
    assert result["clarification_stage"] == "collect_new_topic_question"
    assert result["clarification_expected_input"] == "new_topic_question"
    assert "准备切换到新主题" in result["answer"]
    assert "尚未提供新主题的具体问题" in result["workflow_trace"][2].detail


def test_chat_workflow_requests_clarification_for_same_template_with_different_topic() -> None:
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "question": "员工报销需要什么材料？",
            "message_history": [
                {
                    "role": "user",
                    "content": "员工请假需要什么材料？",
                },
                {
                    "role": "assistant",
                    "content": "员工请假通常需要提交请假单。",
                },
            ],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["fallback_reason"] == "intent_clarification_required"
    assert result["retrieval_count"] == 0
    assert result["citations"] == []
    assert result["clarification_stage"] == "confirm_switch"
    assert "相似问句模板" in result["clarification_reason"]
    assert "主题核心分别为“请假”与“报销”" in result["workflow_trace"][-2].detail


def test_chat_workflow_uses_pending_question_after_clarification_confirmation(
    monkeypatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_retrieve(
        self,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[dict]:
        captured["query"] = query
        return [
            ChatCitation(
                chunk_id="chunk-budget-001",
                document_id="doc-budget-001",
                knowledge_base_id=knowledge_base_id,
                chunk_index=0,
                file_name="团建制度.md",
                content="团建预算需要先提交活动方案，再走部门审批。",
                score=0.91,
                vector_score=0.85,
                lexical_score=0.95,
                embedding_backend="local_hash",
            ).model_dump()
        ]

    def fake_generate(self, **kwargs) -> GeneratedAnswer:
        assert kwargs["question"] == "团建预算怎么申请？"
        return GeneratedAnswer(
            content="团建预算需要先提交活动方案，再走部门审批。[1]",
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=1,
        )

    monkeypatch.setattr(RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        fake_generate,
    )
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "session_status": "awaiting_clarification",
            "session_runtime_context": {
                "current_goal": "员工请假需要做什么？",
                "pending_question": "团建预算怎么申请？",
                "clarification_stage": "confirm_switch",
            },
            "question": "是的",
            "message_history": [
                {
                    "role": "user",
                    "content": "员工请假需要做什么？",
                },
                {
                    "role": "assistant",
                    "content": "员工请假需要提前一天提交申请。",
                },
                {
                    "role": "user",
                    "content": "团建预算怎么申请？",
                },
                {
                    "role": "assistant",
                    "content": "该问题可能偏离当前会话主线，请确认是否切换主题。",
                },
            ],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["fallback_reason"] is None
    assert captured["query"] == "团建预算怎么申请？"
    assert result["current_goal"] == "团建预算怎么申请？"
    assert result["workflow_trace"][4].node == "clarification_router"
    assert result["workflow_trace"][5].node == "clarification_confirm_switch"
    assert "待确认问题“团建预算怎么申请？”继续执行" in result["workflow_trace"][5].detail


def test_chat_workflow_prefers_session_runtime_context_for_clarification_resume(
    monkeypatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_retrieve(
        self,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[dict]:
        captured["query"] = query
        return [
            ChatCitation(
                chunk_id="chunk-budget-ctx-001",
                document_id="doc-budget-ctx-001",
                knowledge_base_id=knowledge_base_id,
                chunk_index=0,
                file_name="团建制度.md",
                content="团建预算需要先提交活动方案，再走部门审批。",
                score=0.9,
                vector_score=0.84,
                lexical_score=0.95,
                embedding_backend="local_hash",
            ).model_dump()
        ]

    def fake_generate(self, **kwargs) -> GeneratedAnswer:
        assert kwargs["question"] == "团建预算怎么申请？"
        return GeneratedAnswer(
            content="团建预算需要先提交活动方案，再走部门审批。[1]",
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=1,
        )

    monkeypatch.setattr(RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        fake_generate,
    )
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "session_status": "awaiting_clarification",
            "session_runtime_context": {
                "current_goal": "员工请假需要做什么？",
                "pending_question": "团建预算怎么申请？",
                "clarification_stage": "confirm_switch",
            },
            "question": "是的",
            "message_history": [
                {
                    "role": "assistant",
                    "content": "该问题可能偏离当前会话主线，请确认是否切换主题。",
                },
            ],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["fallback_reason"] is None
    assert captured["query"] == "团建预算怎么申请？"
    assert result["current_goal"] == "团建预算怎么申请？"


def test_chat_workflow_can_restore_clarification_stage_from_runtime_state(
    monkeypatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_retrieve(
        self,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[dict]:
        captured["query"] = query
        return [
            ChatCitation(
                chunk_id="chunk-budget-runtime-001",
                document_id="doc-budget-runtime-001",
                knowledge_base_id=knowledge_base_id,
                chunk_index=0,
                file_name="团建制度.md",
                content="团建预算需要先提交活动方案，再走部门审批。",
                score=0.91,
                vector_score=0.86,
                lexical_score=0.96,
                embedding_backend="local_hash",
            ).model_dump()
        ]

    def fake_generate(self, **kwargs) -> GeneratedAnswer:
        return GeneratedAnswer(
            content="团建预算需要先提交活动方案，再走部门审批。[1]",
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=1,
        )

    monkeypatch.setattr(RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        fake_generate,
    )
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "session_status": "awaiting_clarification",
            "session_runtime_state": "waiting_clarification_switch",
            "session_runtime_context": {
                "current_goal": "员工请假需要做什么？",
                "pending_question": "团建预算怎么申请？",
            },
            "question": "是的",
            "message_history": [],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["fallback_reason"] is None
    assert captured["query"] == "团建预算怎么申请？"
    assert result["resolved_question"] == "团建预算怎么申请？"


def test_chat_workflow_requests_specific_follow_up_after_rejecting_switch_without_question(
    monkeypatch,
) -> None:
    def should_not_retrieve(self, knowledge_base_id: str, query: str, top_k: int):
        raise AssertionError("未形成具体问题时不应继续检索。")

    def should_not_generate(self, **kwargs):
        raise AssertionError("未形成具体问题时不应继续调用模型生成。")

    monkeypatch.setattr(RetrievalService, "retrieve", should_not_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        should_not_generate,
    )
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "session_status": "awaiting_clarification",
            "session_runtime_context": {
                "current_goal": "员工请假需要做什么？",
                "pending_question": "团建预算怎么申请？",
            },
            "question": "不是，不切换。",
            "message_history": [
                {
                    "role": "assistant",
                    "content": "该问题可能偏离当前会话主线，请确认是否切换主题。",
                },
            ],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["fallback_reason"] == "intent_clarification_required"
    assert result["retrieval_count"] == 0
    assert result["citations"] == []
    assert result["resolved_question"] == ""
    assert result["current_goal"] == "员工请假需要做什么？"
    assert result["clarification_type"] == "continue_current_topic"
    assert result["clarification_stage"] == "collect_current_topic_question"
    assert result["clarification_expected_input"] == "follow_up_question"
    assert "不想切换主题" in result["answer"]
    assert "还没有给出一个可直接检索的具体问题" in result["answer"]
    assert "不足以形成可执行问题" in result["workflow_trace"][-2].detail


def test_chat_workflow_treats_new_question_as_topic_switch_after_clarification(
    monkeypatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_retrieve(
        self,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[dict]:
        captured["query"] = query
        return [
            ChatCitation(
                chunk_id="chunk-002",
                document_id="doc-002",
                knowledge_base_id=knowledge_base_id,
                chunk_index=0,
                file_name="报销制度.md",
                content="员工报销需要提供发票和审批单。",
                score=0.94,
                vector_score=0.87,
                lexical_score=0.98,
                embedding_backend="local_hash",
            ).model_dump()
        ]

    def fake_generate(self, **kwargs) -> GeneratedAnswer:
        assert kwargs["question"] == "员工报销需要什么材料？"
        return GeneratedAnswer(
            content="员工报销需要提供发票和审批单。[1]",
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=1,
        )

    monkeypatch.setattr(RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        fake_generate,
    )
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "session_status": "awaiting_clarification",
            "session_runtime_context": {
                "current_goal": "员工请假需要做什么？",
                "pending_question": "团建预算怎么申请？",
                "clarification_stage": "confirm_switch",
            },
            "question": "员工报销需要什么材料？",
            "message_history": [
                {
                    "role": "user",
                    "content": "员工请假需要做什么？",
                },
                {
                    "role": "assistant",
                    "content": "员工请假需要提前一天提交申请。",
                },
                {
                    "role": "user",
                    "content": "团建预算怎么申请？",
                },
                {
                    "role": "assistant",
                    "content": "该问题可能偏离当前会话主线，请确认是否切换主题。",
                },
            ],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["fallback_reason"] is None
    assert captured["query"] == "员工报销需要什么材料？"
    assert result["current_goal"] == "员工报销需要什么材料？"
    assert result["workflow_trace"][4].node == "clarification_router"
    assert result["workflow_trace"][5].node == "clarification_freeform_router"
    assert result["workflow_trace"][6].node == "clarification_freeform_new_topic"
    assert "主题核心已从“请假”切到“报销”" in result["workflow_trace"][6].detail


def test_chat_workflow_resumes_after_waiting_for_new_topic_question(
    monkeypatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_retrieve(
        self,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[dict]:
        captured["query"] = query
        return [
            ChatCitation(
                chunk_id="chunk-budget-002",
                document_id="doc-budget-002",
                knowledge_base_id=knowledge_base_id,
                chunk_index=0,
                file_name="团建制度.md",
                content="团建预算需要先提交活动方案，再走部门审批。",
                score=0.92,
                vector_score=0.85,
                lexical_score=0.96,
                embedding_backend="local_hash",
            ).model_dump()
        ]

    def fake_generate(self, **kwargs) -> GeneratedAnswer:
        assert kwargs["question"] == "团建预算怎么申请？"
        return GeneratedAnswer(
            content="团建预算需要先提交活动方案，再走部门审批。[1]",
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=1,
        )

    monkeypatch.setattr(RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        fake_generate,
    )
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "session_status": "awaiting_clarification",
            "session_runtime_context": {
                "current_goal": "员工请假需要做什么？",
                "clarification_type": "new_topic_question",
                "clarification_stage": "collect_new_topic_question",
                "clarification_expected_input": "new_topic_question",
            },
            "question": "团建预算怎么申请？",
            "message_history": [
                {
                    "role": "assistant",
                    "content": "请直接补充你要切换到的新问题。",
                },
            ],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["fallback_reason"] is None
    assert captured["query"] == "团建预算怎么申请？"
    assert result["current_goal"] == "团建预算怎么申请？"
    assert result["workflow_trace"][4].node == "clarification_router"
    assert result["workflow_trace"][5].node == "clarification_new_topic"
    assert "用户现已补充新问题“团建预算怎么申请？”" in result["workflow_trace"][
        5
    ].detail


def test_chat_workflow_can_return_to_current_topic_from_new_topic_waiting_state(
    monkeypatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_retrieve(
        self,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[dict]:
        captured["query"] = query
        return [
            ChatCitation(
                chunk_id="chunk-leave-return-001",
                document_id="doc-leave-return-001",
                knowledge_base_id=knowledge_base_id,
                chunk_index=0,
                file_name="请假制度.md",
                content="员工请假通常需要至少提前一天发起申请。",
                score=0.92,
                vector_score=0.86,
                lexical_score=0.97,
                embedding_backend="local_hash",
            ).model_dump()
        ]

    def fake_generate(self, **kwargs) -> GeneratedAnswer:
        assert kwargs["question"] == "请假最晚什么时候提？"
        return GeneratedAnswer(
            content="员工请假通常需要至少提前一天发起申请。[1]",
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=1,
        )

    monkeypatch.setattr(RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        fake_generate,
    )
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "session_status": "awaiting_clarification",
            "session_runtime_context": {
                "current_goal": "员工请假需要做什么？",
                "clarification_type": "new_topic_question",
                "clarification_stage": "collect_new_topic_question",
                "clarification_expected_input": "new_topic_question",
            },
            "question": "继续当前话题：请假最晚什么时候提？",
            "message_history": [
                {
                    "role": "assistant",
                    "content": "请直接补充你要切换到的新问题。",
                },
            ],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["fallback_reason"] is None
    assert captured["query"] == "请假最晚什么时候提？"
    assert result["current_goal"] == "请假最晚什么时候提？"
    assert result["workflow_trace"][4].node == "clarification_router"
    assert result["workflow_trace"][5].node == "clarification_current_topic"
    assert "继续原主线" in result["workflow_trace"][5].detail


def test_chat_workflow_treats_same_template_different_topic_as_switch_after_clarification(
    monkeypatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_retrieve(
        self,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[dict]:
        captured["query"] = query
        return [
            ChatCitation(
                chunk_id="chunk-reimbursement-001",
                document_id="doc-reimbursement-001",
                knowledge_base_id=knowledge_base_id,
                chunk_index=0,
                file_name="报销制度.md",
                content="员工报销需要提供发票和审批单。",
                score=0.94,
                vector_score=0.87,
                lexical_score=0.98,
                embedding_backend="local_hash",
            ).model_dump()
        ]

    def fake_generate(self, **kwargs) -> GeneratedAnswer:
        assert kwargs["question"] == "员工报销需要什么材料？"
        return GeneratedAnswer(
            content="员工报销需要提供发票和审批单。[1]",
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=1,
        )

    monkeypatch.setattr(RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        fake_generate,
    )
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "session_status": "awaiting_clarification",
            "session_runtime_context": {
                "current_goal": "员工请假需要什么材料？",
                "pending_question": "团建预算怎么申请？",
                "clarification_stage": "confirm_switch",
            },
            "question": "员工报销需要什么材料？",
            "message_history": [
                {
                    "role": "assistant",
                    "content": "该问题可能偏离当前会话主线，请确认是否切换主题。",
                },
            ],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["fallback_reason"] is None
    assert captured["query"] == "员工报销需要什么材料？"
    assert result["current_goal"] == "员工报销需要什么材料？"
    assert result["workflow_trace"][4].node == "clarification_router"
    assert result["workflow_trace"][5].node == "clarification_freeform_router"
    assert result["workflow_trace"][6].node == "clarification_freeform_new_topic"
    assert "主题核心已从“请假”切到“报销”" in result["workflow_trace"][6].detail


def test_chat_workflow_rewrites_contextual_follow_up_after_explicit_continue_prefix(
    monkeypatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_retrieve(
        self,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[dict]:
        captured["query"] = query
        return [
            ChatCitation(
                chunk_id="chunk-leave-context-001",
                document_id="doc-leave-context-001",
                knowledge_base_id=knowledge_base_id,
                chunk_index=0,
                file_name="请假制度.md",
                content="员工请假通常需要至少提前一天发起申请。",
                score=0.92,
                vector_score=0.86,
                lexical_score=0.97,
                embedding_backend="local_hash",
            ).model_dump()
        ]

    def fake_generate(self, **kwargs) -> GeneratedAnswer:
        assert kwargs["question"] == "那最晚什么时候提？"
        assert kwargs["effective_question"].startswith("上一轮问题：员工请假需要做什么？")
        return GeneratedAnswer(
            content="员工请假通常需要至少提前一天发起申请。[1]",
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=1,
        )

    monkeypatch.setattr(RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        fake_generate,
    )
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "session_status": "awaiting_clarification",
            "session_runtime_context": {
                "current_goal": "员工请假需要做什么？",
                "clarification_type": "continue_current_topic",
                "clarification_stage": "collect_current_topic_question",
                "clarification_expected_input": "follow_up_question",
            },
            "question": "继续当前话题：那最晚什么时候提？",
            "message_history": [
                {
                    "role": "assistant",
                    "content": "请继续补充你围绕请假主线想问的具体问题。",
                },
            ],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["fallback_reason"] is None
    assert result["resolved_question"] == "那最晚什么时候提？"
    assert result["current_goal"] == "那最晚什么时候提？"
    assert captured["query"].startswith("上一轮问题：员工请假需要做什么？")
    assert result["workflow_trace"][2].node == "question_intake"
    assert "已提取具体问题“那最晚什么时候提？”" in result["workflow_trace"][2].detail
    assert "检索问题已改写为：上一轮问题：员工请假需要做什么？" in result[
        "workflow_trace"
    ][3].detail
    assert result["workflow_trace"][4].node == "clarification_router"
    assert result["workflow_trace"][5].node == "clarification_current_topic"


def test_chat_workflow_rewrites_contextual_follow_up_after_rejecting_switch(
    monkeypatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_retrieve(
        self,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[dict]:
        captured["query"] = query
        return [
            ChatCitation(
                chunk_id="chunk-leave-context-002",
                document_id="doc-leave-context-002",
                knowledge_base_id=knowledge_base_id,
                chunk_index=0,
                file_name="请假制度.md",
                content="员工请假通常需要至少提前一天发起申请。",
                score=0.91,
                vector_score=0.85,
                lexical_score=0.96,
                embedding_backend="local_hash",
            ).model_dump()
        ]

    def fake_generate(self, **kwargs) -> GeneratedAnswer:
        assert kwargs["question"] == "那最晚什么时候提？"
        assert kwargs["effective_question"].startswith("上一轮问题：员工请假需要做什么？")
        return GeneratedAnswer(
            content="员工请假通常需要至少提前一天发起申请。[1]",
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=1,
        )

    monkeypatch.setattr(RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        fake_generate,
    )
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "session_status": "awaiting_clarification",
            "session_runtime_context": {
                "current_goal": "员工请假需要做什么？",
                "clarification_type": "continue_current_topic",
                "clarification_stage": "collect_current_topic_question",
                "clarification_expected_input": "follow_up_question",
            },
            "question": "不是，我是想问那最晚什么时候提？",
            "message_history": [
                {
                    "role": "assistant",
                    "content": "请继续补充你围绕请假主线想问的具体问题。",
                },
            ],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["fallback_reason"] is None
    assert result["resolved_question"] == "那最晚什么时候提？"
    assert result["current_goal"] == "那最晚什么时候提？"
    assert captured["query"].startswith("上一轮问题：员工请假需要做什么？")
    assert result["workflow_trace"][2].node == "question_intake"
    assert "已提取原话题追问“那最晚什么时候提？”" in result["workflow_trace"][2].detail
    assert "检索问题已改写为：上一轮问题：员工请假需要做什么？" in result[
        "workflow_trace"
    ][3].detail
    assert result["workflow_trace"][4].node == "clarification_router"
    assert result["workflow_trace"][5].node == "clarification_current_topic"


def test_chat_workflow_stays_on_current_topic_with_explicit_prefix(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_retrieve(
        self,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[dict]:
        captured["query"] = query
        return [
            ChatCitation(
                chunk_id="chunk-leave-001",
                document_id="doc-leave-001",
                knowledge_base_id=knowledge_base_id,
                chunk_index=0,
                file_name="请假制度.md",
                content="员工请假通常需要至少提前一天发起申请。",
                score=0.92,
                vector_score=0.86,
                lexical_score=0.97,
                embedding_backend="local_hash",
            ).model_dump()
        ]

    def fake_generate(self, **kwargs) -> GeneratedAnswer:
        assert kwargs["question"] == "请假最晚什么时候提？"
        return GeneratedAnswer(
            content="员工请假通常需要至少提前一天发起申请。[1]",
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=1,
        )

    monkeypatch.setattr(RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        fake_generate,
    )
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "session_status": "awaiting_clarification",
            "session_runtime_context": {
                "current_goal": "员工请假需要做什么？",
                "pending_question": "团建预算怎么申请？",
                "clarification_stage": "confirm_switch",
            },
            "question": "继续当前话题：请假最晚什么时候提？",
            "message_history": [
                {
                    "role": "assistant",
                    "content": "该问题可能偏离当前会话主线，请确认是否切换主题。",
                },
            ],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["fallback_reason"] is None
    assert captured["query"] == "请假最晚什么时候提？"
    assert result["current_goal"] == "请假最晚什么时候提？"
    assert result["workflow_trace"][4].node == "clarification_router"
    assert result["workflow_trace"][5].node == "clarification_current_topic"
    assert "并补充本轮问题“请假最晚什么时候提？”" in result["workflow_trace"][5].detail


def test_chat_workflow_continues_current_topic_after_rejecting_switch(
    monkeypatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_retrieve(
        self,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[dict]:
        captured["query"] = query
        return [
            ChatCitation(
                chunk_id="chunk-leave-002",
                document_id="doc-leave-002",
                knowledge_base_id=knowledge_base_id,
                chunk_index=0,
                file_name="请假制度.md",
                content="员工请假通常需要至少提前一天发起申请。",
                score=0.91,
                vector_score=0.85,
                lexical_score=0.96,
                embedding_backend="local_hash",
            ).model_dump()
        ]

    def fake_generate(self, **kwargs) -> GeneratedAnswer:
        assert kwargs["question"] == "请假最晚什么时候提？"
        return GeneratedAnswer(
            content="员工请假通常需要至少提前一天发起申请。[1]",
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=1,
        )

    monkeypatch.setattr(RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        fake_generate,
    )
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "session_status": "awaiting_clarification",
            "session_runtime_context": {
                "current_goal": "员工请假需要做什么？",
                "pending_question": "团建预算怎么申请？",
                "clarification_stage": "confirm_switch",
            },
            "question": "不是，我是想问请假最晚什么时候提？",
            "message_history": [
                {
                    "role": "assistant",
                    "content": "该问题可能偏离当前会话主线，请确认是否切换主题。",
                },
            ],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["fallback_reason"] is None
    assert captured["query"] == "请假最晚什么时候提？"
    assert result["current_goal"] == "请假最晚什么时候提？"
    assert result["workflow_trace"][4].node == "clarification_router"
    assert result["workflow_trace"][5].node == "clarification_current_topic"
    assert "明确表示不切换主题" in result["workflow_trace"][5].detail


def test_chat_workflow_allows_explicit_topic_switch(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_retrieve(
        self,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[dict]:
        captured["query"] = query
        return [
            ChatCitation(
                chunk_id="chunk-001",
                document_id="doc-001",
                knowledge_base_id=knowledge_base_id,
                chunk_index=0,
                file_name="报销制度.md",
                content="员工报销需要提供发票和审批单。",
                score=0.94,
                vector_score=0.87,
                lexical_score=0.98,
                embedding_backend="local_hash",
            ).model_dump()
        ]

    def fake_generate(self, **kwargs) -> GeneratedAnswer:
        assert kwargs["current_goal"] == "报销需要什么材料？"
        assert kwargs["question"] == "报销需要什么材料？"
        return GeneratedAnswer(
            content="员工报销需要提供发票和审批单。[1]",
            model_name="mock-gpt",
            backend_name="mock-backend",
            citation_count=1,
        )

    monkeypatch.setattr(RetrievalService, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        "app.services.answer_generation.AnswerGenerationService.generate_answer",
        fake_generate,
    )
    workflow = build_chat_workflow(include_compose_answer=True)

    result = workflow.invoke(
        {
            "assistant_id": "asst-test-001",
            "assistant_name": "测试助理",
            "assistant_config": {
                "assistant_id": "asst-test-001",
                "assistant_name": "测试助理",
                "system_prompt": "请用中文回答。",
                "default_model": "gpt-4o-mini",
                "default_kb_ids": ["kb-default-001"],
            },
            "question": "换个问题，报销需要什么材料？",
            "message_history": [
                {
                    "role": "user",
                    "content": "员工请假需要做什么？",
                },
                {
                    "role": "assistant",
                    "content": "员工请假需要提前一天提交申请。",
                },
            ],
            "requested_knowledge_base_ids": [],
            "top_k": 3,
        }
    )

    assert result["fallback_reason"] is None
    assert captured["query"] == "报销需要什么材料？"
    assert result["workflow_trace"][2].node == "question_intake"
    assert "识别到显式切换主题指令" in result["workflow_trace"][2].detail
    assert result["workflow_trace"][5].node == "intent_guard"
    assert "按问题“报销需要什么材料？”继续执行" in result["workflow_trace"][5].detail
