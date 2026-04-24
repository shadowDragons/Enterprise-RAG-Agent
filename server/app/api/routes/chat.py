import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.api.deps.auth import require_permissions
from app.db.session import SessionLocal, get_db
from app.repositories.assistants import AssistantRepository
from app.repositories.knowledge_bases import KnowledgeBaseRepository
from app.repositories.messages import MessageRepository
from app.repositories.sessions import SessionRepository
from app.schemas.chat import ChatQueryRequest, WorkflowTraceStep
from app.schemas.message import MessageSummary, to_message_summary
from app.services.answer_generation import (
    AnswerGenerationError,
    AnswerGenerationService,
    AnswerGenerationUnavailableError,
    build_intent_clarification_answer,
    build_no_knowledge_base_answer,
    build_no_retrieval_hits_answer,
    build_review_required_answer,
)
from app.services.chat_rag import PreparedWorkflowData, SessionChatService

router = APIRouter(
    prefix="/sessions",
    tags=["chat"],
    dependencies=[Depends(require_permissions("session:read"))],
)


def _normalize_requested_kb_ids(payload: ChatQueryRequest) -> list[str]:
    candidates = []
    if payload.knowledge_base_id:
        candidates.append(payload.knowledge_base_id)
    candidates.extend(payload.knowledge_base_ids)
    return list(
        dict.fromkeys(item.strip() for item in candidates if item and item.strip())
    )


def _resolve_chat_context(
    db: Session,
    session_id: str,
    payload: ChatQueryRequest,
):
    # 统一校验会话、助理，以及用户本轮显式指定的知识库是否存在。
    session_repository = SessionRepository(db)
    session = session_repository.get(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在。",
        )

    assistant_repository = AssistantRepository(db)
    assistant = assistant_repository.get(session.assistant_id)
    if not assistant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="助理不存在。",
        )

    requested_knowledge_base_ids = _normalize_requested_kb_ids(payload)
    if requested_knowledge_base_ids:
        knowledge_base_repository = KnowledgeBaseRepository(db)
        for knowledge_base_id in requested_knowledge_base_ids:
            knowledge_base = knowledge_base_repository.get(knowledge_base_id)
            if not knowledge_base:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"知识库不存在：{knowledge_base_id}",
                )

    return session, assistant, requested_knowledge_base_ids


def _format_sse_event(event: str, data: dict) -> str:
    # SSE 协议的最小格式：event + data + 空行。
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.get("/{session_id}/messages", response_model=list[MessageSummary])
async def list_session_messages(
    session_id: str,
    db: Session = Depends(get_db),
) -> list[MessageSummary]:
    session_repository = SessionRepository(db)
    session = session_repository.get(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在。",
        )

    repository = MessageRepository(db)
    return [to_message_summary(item) for item in repository.list(session_id=session_id)]


@router.post(
    "/{session_id}/chat/stream",
    dependencies=[Depends(require_permissions("chat:write"))],
)
async def stream_session_chat(
    session_id: str,
    payload: ChatQueryRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    # 先用当前请求的 db 做一次入口校验，尽早返回明确错误。
    session, assistant, requested_knowledge_base_ids = _resolve_chat_context(
        db,
        session_id,
        payload,
    )
    assistant_id = assistant.assistant_id

    def event_stream():
        try:
            # 流式响应会持续一段时间，这里单独开一个 db session，
            # 避免直接持有依赖注入的 db 到整个流结束。
            with SessionLocal() as stream_db:
                session = SessionRepository(stream_db).get(session_id)
                assistant = AssistantRepository(stream_db).get(assistant_id)
                if not session or not assistant:
                    yield _format_sse_event("error", {"message": "会话或助理不存在。"})
                    return

                service = SessionChatService(stream_db)
                # 先完成检索上下文准备；这一步会先写入 user 消息。
                prepared_context = service.prepare_stream_context(
                    session=session,
                    assistant=assistant,
                    question=payload.question,
                    requested_knowledge_base_ids=requested_knowledge_base_ids,
                    top_k=payload.top_k,
                )
                # 通知前端流式输出正式开始，并携带本次检索的基础上下文。
                yield _format_sse_event(
                    "start",
                    {
                        "session_id": prepared_context.session_id,
                        "selected_knowledge_base_id": prepared_context.selected_knowledge_base_id,
                        "selected_kb_ids": prepared_context.selected_kb_ids,
                        "retrieval_count": prepared_context.retrieval_count,
                    },
                )

                answer_stream = _stream_or_fallback_answer(
                    service=service,
                    prepared_context=prepared_context,
                    assistant=assistant,
                )
                while True:
                    try:
                        yield next(answer_stream)
                    except StopIteration as stop:
                        prepared_result = stop.value
                        break

                # 只有流完整结束后，才把 assistant 消息正式落库。
                prepared_result = service.finalize_turn(
                    session=session,
                    assistant=assistant,
                    prepared=prepared_result,
                )
                yield _format_sse_event(
                    "completed",
                    service.to_response(prepared_result).model_dump(mode="json"),
                )
        except GeneratorExit:
            # 前端主动中断时，不把它当成服务端错误。
            return
        except AnswerGenerationUnavailableError as exc:
            yield _format_sse_event(
                "error",
                {"message": f"当前未配置可用的聊天模型：{exc}"},
            )
        except AnswerGenerationError as exc:
            yield _format_sse_event(
                "error",
                {"message": f"聊天模型生成失败：{exc}"},
            )
        except Exception as exc:  # pragma: no cover
            yield _format_sse_event("error", {"message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _stream_or_fallback_answer(
    *,
    service: SessionChatService,
    prepared_context: PreparedWorkflowData,
    assistant,
):
    if prepared_context.fallback_reason == "no_knowledge_base_selected":
        answer = build_no_knowledge_base_answer(
            assistant_name=assistant.assistant_name,
            question=prepared_context.resolved_question,
        )
        workflow_trace = _append_trace(
            prepared_context.workflow_trace,
            node="compose_answer",
            detail="未进入检索，流式接口直接返回知识库范围缺失的兜底回答。",
        )
        result = service.build_result(
            context=prepared_context,
            answer=answer,
            fallback_reason=prepared_context.fallback_reason,
            workflow_trace=workflow_trace,
        )
        yield from _iter_text_chunk_events(answer)
        return result

    if prepared_context.fallback_reason == "review_required":
        answer = build_review_required_answer(
            assistant_name=assistant.assistant_name,
            question=prepared_context.resolved_question,
            review_reason=prepared_context.review_reason or "命中人工复核规则",
        )
        result = service.build_result(
            context=prepared_context,
            answer=answer,
            fallback_reason=prepared_context.fallback_reason,
        )
        yield from _iter_text_chunk_events(answer)
        return result

    if prepared_context.fallback_reason == "intent_clarification_required":
        answer = build_intent_clarification_answer(
            assistant_name=assistant.assistant_name,
            question=prepared_context.question,
            current_goal=prepared_context.current_goal or prepared_context.question,
            drift_reason=(
                prepared_context.clarification_reason or "当前问题与会话主线关联较弱"
            ),
            clarification_type=prepared_context.clarification_type or "confirm_switch",
        )
        workflow_trace = _append_trace(
            prepared_context.workflow_trace,
            node="compose_answer",
            detail="检测到会话主线可能漂移，流式接口返回澄清提示。",
        )
        result = service.build_result(
            context=prepared_context,
            answer=answer,
            fallback_reason=prepared_context.fallback_reason,
            workflow_trace=workflow_trace,
        )
        yield from _iter_text_chunk_events(answer)
        return result

    if not prepared_context.citations:
        answer = build_no_retrieval_hits_answer(
            assistant_name=assistant.assistant_name,
            question=prepared_context.resolved_question,
            selected_kb_ids=prepared_context.selected_kb_ids,
            selected_knowledge_base_id=prepared_context.selected_knowledge_base_id,
        )
        workflow_trace = _append_trace(
            prepared_context.workflow_trace,
            node="compose_answer",
            detail="检索结果为空，流式接口返回无命中兜底回答。",
        )
        result = service.build_result(
            context=prepared_context,
            answer=answer,
            fallback_reason=None,
            workflow_trace=workflow_trace,
        )
        yield from _iter_text_chunk_events(answer)
        return result

    answer_generation = AnswerGenerationService()
    stream = answer_generation.stream_answer(
        assistant_name=assistant.assistant_name,
        system_prompt=assistant.system_prompt,
        question=prepared_context.resolved_question,
        effective_question=prepared_context.effective_question,
        current_goal=prepared_context.current_goal,
        memory_summary=prepared_context.memory_summary,
        citations=prepared_context.citations,
        selected_kb_ids=prepared_context.selected_kb_ids,
        selected_knowledge_base_id=prepared_context.selected_knowledge_base_id,
        model_name=assistant.default_model,
    )

    try:
        while True:
            chunk = next(stream)
            yield _format_sse_event("chunk", {"delta": chunk.delta})
    except StopIteration as stop:
        generated = stop.value
        workflow_trace = _append_trace(
            prepared_context.workflow_trace,
            node="compose_answer",
            detail=(
                f"已调用模型 {generated.model_name} 流式生成答案，"
                f"使用后端 {generated.backend_name}，"
                f"参考 {generated.citation_count} 条引用片段。"
            ),
        )
        result = service.build_result(
            context=prepared_context,
            answer=generated.content,
            fallback_reason=None,
            workflow_trace=workflow_trace,
        )
        return result


def _iter_text_chunk_events(text: str, *, chunk_size: int = 24):
    for index in range(0, len(text), chunk_size):
        delta = text[index : index + chunk_size]
        yield _format_sse_event("chunk", {"delta": delta})


def _append_trace(
    workflow_trace: list[WorkflowTraceStep],
    *,
    node: str,
    detail: str,
) -> list[WorkflowTraceStep]:
    trace = list(workflow_trace)
    trace.append(WorkflowTraceStep(node=node, detail=detail))
    return trace
