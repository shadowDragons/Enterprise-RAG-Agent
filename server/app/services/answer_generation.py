from collections.abc import Generator
from dataclasses import dataclass

from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import get_settings
from app.integrations.chat_model_provider import (
    ChatModelInvocationError,
    ChatModelService,
    ChatModelUnavailableError,
)
from app.schemas.chat import ChatCitation


class AnswerGenerationUnavailableError(RuntimeError):
    """当前环境不具备真实模型生成能力时抛出。"""


class AnswerGenerationError(RuntimeError):
    """真实模型生成失败。"""


@dataclass
class GeneratedAnswer:
    content: str
    model_name: str
    backend_name: str
    citation_count: int


@dataclass
class AnswerGenerationChunk:
    delta: str
    model_name: str
    backend_name: str


class AnswerGenerationService:
    """把检索片段整理成 Prompt，并调用聊天模型生成最终回答。"""

    def __init__(self, model_service: ChatModelService | None = None) -> None:
        self.settings = get_settings()
        self.model_service = model_service or ChatModelService()

    def generate_answer(
        self,
        *,
        assistant_name: str,
        system_prompt: str,
        question: str,
        effective_question: str = "",
        current_goal: str = "",
        memory_summary: str = "",
        citations: list[ChatCitation],
        selected_kb_ids: list[str],
        selected_knowledge_base_id: str,
        model_name: str,
    ) -> GeneratedAnswer:
        if not citations:
            raise AnswerGenerationError("没有可用引用片段，无法生成答案。")

        messages = self.build_messages(
            assistant_name=assistant_name,
            system_prompt=system_prompt,
            question=question,
            effective_question=effective_question,
            current_goal=current_goal,
            memory_summary=memory_summary,
            citations=citations,
            selected_kb_ids=selected_kb_ids,
            selected_knowledge_base_id=selected_knowledge_base_id,
        )

        last_error: Exception | None = None
        for candidate_model in self._candidate_models(model_name):
            try:
                response = self.model_service.invoke(
                    messages=messages,
                    model=candidate_model,
                    temperature=self.settings.llm_temperature,
                )
                answer = response.content.strip()
                if not answer:
                    raise AnswerGenerationError("聊天模型返回了空回答。")
                return GeneratedAnswer(
                    content=answer,
                    model_name=response.model_name or candidate_model,
                    backend_name=response.backend_name,
                    citation_count=min(
                        len(citations),
                        self.settings.llm_max_context_citations,
                    ),
                )
            except ChatModelUnavailableError as exc:
                raise AnswerGenerationUnavailableError(str(exc)) from exc
            except ChatModelInvocationError as exc:
                last_error = exc

        if last_error:
            raise AnswerGenerationError(str(last_error)) from last_error
        raise AnswerGenerationUnavailableError("当前未配置可用的聊天模型。")

    def stream_answer(
        self,
        *,
        assistant_name: str,
        system_prompt: str,
        question: str,
        effective_question: str = "",
        current_goal: str = "",
        memory_summary: str = "",
        citations: list[ChatCitation],
        selected_kb_ids: list[str],
        selected_knowledge_base_id: str,
        model_name: str,
    ) -> Generator[AnswerGenerationChunk, None, GeneratedAnswer]:
        if not citations:
            raise AnswerGenerationError("没有可用引用片段，无法生成答案。")

        messages = self.build_messages(
            assistant_name=assistant_name,
            system_prompt=system_prompt,
            question=question,
            effective_question=effective_question,
            current_goal=current_goal,
            memory_summary=memory_summary,
            citations=citations,
            selected_kb_ids=selected_kb_ids,
            selected_knowledge_base_id=selected_knowledge_base_id,
        )

        last_error: Exception | None = None
        for candidate_model in self._candidate_models(model_name):
            resolved_model_name = candidate_model
            backend_name = self.model_service.describe_backend()
            emitted_any_chunk = False
            content_parts: list[str] = []

            try:
                for chunk in self.model_service.stream(
                    messages=messages,
                    model=candidate_model,
                    temperature=self.settings.llm_temperature,
                ):
                    emitted_any_chunk = True
                    resolved_model_name = chunk.model_name or resolved_model_name
                    backend_name = chunk.backend_name or backend_name
                    content_parts.append(chunk.delta)
                    yield AnswerGenerationChunk(
                        delta=chunk.delta,
                        model_name=resolved_model_name,
                        backend_name=backend_name,
                    )
            except ChatModelUnavailableError as exc:
                raise AnswerGenerationUnavailableError(str(exc)) from exc
            except ChatModelInvocationError as exc:
                if emitted_any_chunk:
                    raise AnswerGenerationError(str(exc)) from exc
                last_error = exc
                continue

            answer = "".join(content_parts).strip()
            if not answer:
                last_error = AnswerGenerationError("聊天模型流式返回了空回答。")
                continue

            return GeneratedAnswer(
                content=answer,
                model_name=resolved_model_name,
                backend_name=backend_name,
                citation_count=min(
                    len(citations),
                    self.settings.llm_max_context_citations,
                ),
            )

        if last_error:
            raise AnswerGenerationError(str(last_error)) from last_error
        raise AnswerGenerationUnavailableError("当前未配置可用的聊天模型。")

    def build_messages(
        self,
        *,
        assistant_name: str,
        system_prompt: str,
        question: str,
        effective_question: str = "",
        current_goal: str = "",
        memory_summary: str = "",
        citations: list[ChatCitation],
        selected_kb_ids: list[str],
        selected_knowledge_base_id: str,
    ) -> list[BaseMessage]:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "你是企业级知识库助理“{assistant_name}”。\n"
                        "请严格基于提供的引用片段回答，不要编造制度、流程或数字。\n"
                        "回答要求：\n"
                        "1. 使用简体中文，先直接回答问题，再补充关键依据。\n"
                        "2. 仅在引用片段支持的范围内下结论；信息不足时要明确说明。\n"
                        "3. 适合企业产品界面展示，表达简洁、专业。\n"
                        "4. 如有帮助，可在句末使用 [1] [2] 这样的引用编号。\n"
                        "5. 如果存在多轮对话上下文，请优先保持和当前会话目标一致。\n"
                        "附加助理指令：\n"
                        "{normalized_system_prompt}"
                    ),
                ),
                (
                    "human",
                    (
                        "用户问题：\n{question}\n\n"
                        "检索使用的问题：\n{effective_question}\n\n"
                        "当前会话目标：\n{current_goal}\n\n"
                        "最近对话记忆：\n{memory_summary}\n\n"
                        "本轮知识库范围：\n{kb_scope_label}\n\n"
                        "可用引用片段：\n{citation_context}\n\n"
                        "请输出最终回答。"
                    ),
                ),
            ]
        )
        return prompt.invoke(
            {
                "assistant_name": assistant_name or "企业知识库助理",
                "normalized_system_prompt": self._normalize_system_prompt(
                    system_prompt
                ),
                "question": question.strip(),
                "effective_question": (effective_question or question).strip(),
                "current_goal": (current_goal or question).strip(),
                "memory_summary": self._normalize_memory_summary(memory_summary),
                "kb_scope_label": self._format_kb_scope_label(
                    selected_kb_ids=selected_kb_ids,
                    selected_knowledge_base_id=selected_knowledge_base_id,
                ),
                "citation_context": self._format_citation_context(citations),
            }
        ).to_messages()

    def _candidate_models(self, preferred_model: str) -> list[str]:
        candidates: list[str] = []
        for item in (preferred_model.strip(), self.settings.llm_model.strip()):
            if item and item not in candidates:
                candidates.append(item)
        return candidates

    def _format_kb_scope_label(
        self,
        *,
        selected_kb_ids: list[str],
        selected_knowledge_base_id: str,
    ) -> str:
        if selected_kb_ids:
            return "、".join(selected_kb_ids)
        return selected_knowledge_base_id or "未显式指定"

    def _normalize_system_prompt(self, system_prompt: str) -> str:
        prompt = system_prompt.strip()
        if prompt:
            return prompt
        return "未额外配置自定义 system prompt。"

    def _normalize_memory_summary(self, memory_summary: str) -> str:
        summary = memory_summary.strip()
        if summary:
            return summary
        return "当前没有可用的历史对话记忆。"

    def _format_citation_context(self, citations: list[ChatCitation]) -> str:
        lines: list[str] = []
        for index, citation in enumerate(
            citations[: self.settings.llm_max_context_citations],
            start=1,
        ):
            excerpt = citation.content.replace("\n", " ").strip()
            lines.append(
                (
                    f"[{index}] 知识库：{citation.knowledge_base_id}\n"
                    f"文档：{citation.file_name or citation.document_id}\n"
                    f"片段：{excerpt}"
                )
            )
        return "\n\n".join(lines)


def build_no_knowledge_base_answer(*, assistant_name: str, question: str) -> str:
    return (
        f"{assistant_name} 当前还没有可用的知识库范围，暂时无法回答“{question}”。"
        "你可以先为助理绑定知识库，或者在本轮手动选择知识库后再提问。"
    )


def build_no_retrieval_hits_answer(
    *,
    assistant_name: str,
    question: str,
    selected_kb_ids: list[str],
    selected_knowledge_base_id: str,
) -> str:
    kb_scope_label = (
        "、".join(selected_kb_ids)
        if selected_kb_ids
        else (selected_knowledge_base_id or "默认范围")
    )
    return (
        f"{assistant_name} 当前没有在知识库范围 {kb_scope_label} "
        f"中检索到与“{question}”直接相关的内容。"
        "你可以换个问法，或者先上传更相关的文档。"
    )


def build_intent_clarification_answer(
    *,
    assistant_name: str,
    question: str,
    current_goal: str,
    drift_reason: str,
    clarification_type: str = "confirm_switch",
) -> str:
    if clarification_type == "new_topic_question":
        return (
            f"{assistant_name or '知识库助理'} 已理解你准备切换到新主题，"
            "但这次消息里还没有包含可直接处理的具体问题。\n"
            "请直接补充新的问题，例如“团建预算怎么申请？”或"
            "“员工报销需要什么材料？”。"
        )
    if clarification_type == "continue_current_topic":
        return (
            f"{assistant_name or '知识库助理'} 已理解你当前不想切换主题，"
            f"仍然要围绕会话主线“{current_goal}”继续提问。\n"
            f"原因：{drift_reason}。\n"
            "但你这次回复里还没有给出一个可直接检索的具体问题。"
            "请直接补充你想继续追问的内容，例如“继续当前话题：请假最晚什么时候提？”"
            "或“我是想问这个流程需要谁审批？”。"
        )
    return (
        f"{assistant_name or '知识库助理'} 判断你当前的问题“{question}”"
        f"可能已经偏离本次会话主线“{current_goal}”。\n"
        f"原因：{drift_reason}。\n"
        "如果你是想继续围绕当前主线追问，请补充更具体的上下文；"
        "如果你确认要切换到新主题，可以直接明确说明“切换到新问题：...”，"
        "我会按新主题继续处理。"
    )


def build_review_required_answer(
    *,
    assistant_name: str,
    question: str,
    review_reason: str,
) -> str:
    return (
        f"{assistant_name or '知识库助理'} 判断当前问题“{question}”命中了人工复核规则，"
        f"原因：{review_reason}。\n"
        "为避免自动回答造成误导，本轮已暂停直接生成结论。"
        "请结合企业制度原文或由管理员人工复核后再回复。"
    )


def build_review_rejected_answer(
    *,
    question: str,
    reviewer_note: str,
    manual_answer: str,
) -> str:
    if manual_answer:
        return manual_answer
    if reviewer_note:
        return (
            f"针对问题“{question}”，人工审核未通过自动回答。\n"
            f"审核意见：{reviewer_note}"
        )
    return f"针对问题“{question}”，人工审核未通过自动回答，请转人工继续处理。"

