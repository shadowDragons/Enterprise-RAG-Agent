# `event_stream` 问答代码链路梳理

本文梳理后端流式问答入口 `event_stream` 的完整执行链路，覆盖：

- HTTP 入口
- `SessionChatService` 预处理
- LangGraph workflow 节点流转
- SSE 事件输出
- assistant 消息落库
- session 运行态更新
- review 中断与恢复

相关入口代码：

- 路由入口：[server/app/api/routes/chat.py](server/app/api/routes/chat.py)
- 服务层：[server/app/services/chat_rag.py](server/app/services/chat_rag.py)
- workflow 拓扑：[server/app/workflows/chat_graph.py](server/app/workflows/chat_graph.py)
- 澄清与意图守卫：[server/app/workflows/chat_graph_clarification.py](server/app/workflows/chat_graph_clarification.py)
- 检索与 review：[server/app/workflows/chat_graph_execution.py](server/app/workflows/chat_graph_execution.py)
- workflow 公共状态与意图判断：[server/app/workflows/chat_graph_support.py](server/app/workflows/chat_graph_support.py)

## 1. 总体结构

`event_stream` 不是直接让 LangGraph 边跑边吐模型 token，而是一个“两段式”链路：

1. 先执行一次不包含 `compose_answer` 的 workflow，产出 `PreparedWorkflowData`
2. 再由路由层 `_stream_or_fallback_answer()` 决定：
   - 直接返回兜底文本
   - 或调用 `AnswerGenerationService.stream_answer()` 做真正的流式输出

对应代码：

- `stream_session_chat()` / `event_stream()`：
  [server/app/api/routes/chat.py](server/app/api/routes/chat.py)
- `prepare_stream_context()`：
  [server/app/services/chat_rag.py](server/app/services/chat_rag.py)
- `build_chat_workflow(include_compose_answer=False)`：
  [server/app/services/chat_rag.py](server/app/services/chat_rag.py)
  [server/app/workflows/chat_graph.py](server/app/workflows/chat_graph.py)

## 2. 入口到流式输出的主链路

### 2.1 HTTP 路由入口

入口函数是 `stream_session_chat()`。

位置：

- [server/app/api/routes/chat.py](server/app/api/routes/chat.py)

主要职责：

- 校验 `session_id` 对应会话是否存在
- 校验会话绑定的 assistant 是否存在
- 校验本轮用户显式指定的知识库是否存在
- 保存 `assistant_id`，供后续长连接里的独立数据库 session 使用

关键辅助函数：

- `_normalize_requested_kb_ids()`
- `_resolve_chat_context()`

### 2.2 创建独立的流式数据库 session

`event_stream()` 内部会重新 `with SessionLocal() as stream_db`。

位置：

- [server/app/api/routes/chat.py](server/app/api/routes/chat.py)

这样做的目的：

- 避免直接持有 FastAPI 依赖注入的 db 到整个 SSE 生命周期结束
- 保证长连接期间读写数据库的生命周期独立

### 2.3 预处理上下文

`event_stream()` 中会创建 `SessionChatService(stream_db)`，然后调用：

```python
prepared_context = service.prepare_stream_context(...)
```

位置：

- [server/app/api/routes/chat.py](server/app/api/routes/chat.py)
- [server/app/services/chat_rag.py](server/app/services/chat_rag.py)

这里的返回值是 `PreparedWorkflowData`，它不是最终答案，而是回答生成前的完整上下文快照，包含：

- `question`
- `resolved_question`
- `effective_question`
- `current_goal`
- `memory_summary`
- `selected_kb_ids`
- `citations`
- `retrieval_count`
- `fallback_reason`
- `workflow_trace`

定义位置：

- [server/app/services/chat_rag.py](server/app/services/chat_rag.py)

### 2.4 发出 `start` 事件

上下文准备完成后，路由会先发一个 SSE `start` 事件。

位置：

- [server/app/api/routes/chat.py](server/app/api/routes/chat.py)

携带字段：

- `session_id`
- `selected_knowledge_base_id`
- `selected_kb_ids`
- `retrieval_count`

### 2.5 进入 `_stream_or_fallback_answer()`

`event_stream()` 随后进入：

```python
answer_stream = _stream_or_fallback_answer(...)
```

位置：

- [server/app/api/routes/chat.py](server/app/api/routes/chat.py)

这一步决定本轮究竟是：

- 直接规则化兜底输出
- 还是调用模型流式生成

### 2.6 落库与 `completed`

当 `_stream_or_fallback_answer()` 结束时，会返回 `PreparedChatResult`。

之后执行：

```python
prepared_result = service.finalize_turn(...)
```

位置：

- [server/app/api/routes/chat.py](server/app/api/routes/chat.py)
- [server/app/services/chat_rag.py](server/app/services/chat_rag.py)

`finalize_turn()` 负责：

- assistant 消息正式落库
- 更新 `session.status` 与 runtime 字段
- 写入 audit log
- 如果命中 review，则创建 review task

最后路由发出 SSE `completed` 事件。

## 3. `prepare_stream_context()` 内部链路

### 3.1 `SessionChatService` 初始化

`SessionChatService.__init__()` 内部会构建一个“预处理 workflow”：

```python
self.preparation_workflow = build_chat_workflow(
    include_compose_answer=False,
    checkpointer=checkpointer,
)
```

位置：

- [server/app/services/chat_rag.py](server/app/services/chat_rag.py)

含义：

- workflow 会跑到检索、review gate、clarification 判定为止
- 不会在 graph 内部直接生成最终回答

### 3.2 `_invoke_workflow()`

`prepare_stream_context()` 最终调用 `_invoke_workflow()`。

位置：

- [server/app/services/chat_rag.py](server/app/services/chat_rag.py)

执行顺序如下。

#### 第一步：读取历史消息

通过 `_load_recent_messages()` 从消息表中读取最近若干条历史消息。

位置：

- [server/app/services/chat_rag.py](server/app/services/chat_rag.py)
- [server/app/repositories/messages.py](server/app/repositories/messages.py)

这批消息会作为 `message_history` 传入 workflow。

#### 第二步：写入本轮 user 消息

`_start_turn()` 会先把当前问题按 `role="user"` 写入消息表。

位置：

- [server/app/services/chat_rag.py](server/app/services/chat_rag.py)
- [server/app/repositories/messages.py](server/app/repositories/messages.py)

这里还有两个关键点：

- 如果当前会话标题是 `新会话`，会用当前问题前 20 个字符更新标题
- `user_message.message_id` 被复用为 `workflow_thread_id`

也就是说，这个 `workflow_thread_id` 既是“本轮用户消息 ID”，也是 LangGraph checkpointer 的线程 ID。

#### 第三步：组装 workflow 输入

`_build_workflow_input()` 会把以下内容塞进 graph state：

- assistant 基本信息与配置
- `session_status`
- `session_runtime_context`
- `session_runtime_state`
- `question`
- `requested_knowledge_base_ids`
- `message_history`
- `top_k`
- `review_interrupt_enabled=True`

位置：

- [server/app/services/chat_rag.py](server/app/services/chat_rag.py)

#### 第四步：执行 workflow

执行：

```python
workflow.invoke(..., config={"configurable": {"thread_id": workflow_thread_id}})
```

位置：

- [server/app/services/chat_rag.py](server/app/services/chat_rag.py)

如果后续命中 review `interrupt`，就是靠这个 `thread_id` 继续恢复。

#### 第五步：构造 `PreparedWorkflowData`

执行结束后，`_build_prepared_workflow_data()` 把 workflow result 收敛成服务层统一结构。

位置：

- [server/app/services/chat_rag.py](server/app/services/chat_rag.py)

这里会做一个重要处理：

- 如果 workflow 返回了 `__interrupt__`
- 就把 `fallback_reason` 强制视为 `review_required`

## 4. Workflow 拓扑

workflow 的组装入口在：

- [server/app/workflows/chat_graph.py](server/app/workflows/chat_graph.py)

主干拓扑是：

```text
START
 -> assistant_config
 -> kb_scope
 -> question_intake
 -> memory_manager
 -> clarification_router
 -> (clarification 分支)
 -> intent_guard
 -> retrieve_context
 -> review_gate
 -> review_hold
 -> compose_answer（仅 include_compose_answer=True 时存在）
 -> END
```

当前 `event_stream` 使用的是 `include_compose_answer=False`，所以 graph 只负责“准备上下文”，最终回答生成不在 graph 里。

## 5. 各节点职责

### 5.1 `assistant_config`

位置：

- [server/app/workflows/chat_graph_clarification.py](server/app/workflows/chat_graph_clarification.py)

作用：

- 从 `assistant_config` 里提取 assistant 基本配置
- 初始化 `selected_kb_ids`
- 写一条 `workflow_trace`

### 5.2 `kb_scope`

位置：

- [server/app/workflows/chat_graph_clarification.py](server/app/workflows/chat_graph_clarification.py)

作用：

- 优先使用用户本轮显式传入的 `requested_knowledge_base_ids`
- 否则使用 assistant 默认知识库 `default_kb_ids`
- 截断到 `settings.max_chat_selected_kb_count`
- 选出首个 `selected_knowledge_base_id`

如果没有可用知识库，会直接设置：

- `fallback_reason = "no_knowledge_base_selected"`
- `citations = []`
- `retrieval_count = 0`

### 5.3 `question_intake`

位置：

- [server/app/workflows/chat_graph_clarification.py](server/app/workflows/chat_graph_clarification.py)
- [server/app/workflows/chat_graph_support.py](server/app/workflows/chat_graph_support.py)

作用：

- 解析本轮问题中的控制语义
- 识别是否是：
  - 显式切题
  - 继续当前话题
  - 拒绝切题
  - 确认切题

输出关键字段：

- `raw_question`
- `normalized_question`
- `question_control_action`

### 5.4 `memory_manager`

位置：

- [server/app/workflows/chat_graph_clarification.py](server/app/workflows/chat_graph_clarification.py)
- [server/app/workflows/chat_graph_support.py](server/app/workflows/chat_graph_support.py)

作用：

- 根据历史消息和当前 session 运行态，推断 `current_goal`
- 构造 `memory_summary`
- 根据是否像追问，计算 `effective_question`

这里要区分两个概念：

- `resolved_question`：本轮最终要处理的问题
- `effective_question`：给检索层使用的问题，可能被改写成“上一轮问题 + 当前追问”

### 5.5 `clarification_router`

位置：

- [server/app/workflows/chat_graph_clarification.py](server/app/workflows/chat_graph_clarification.py)

作用：

- 如果当前 session 不在 `awaiting_clarification`，直接跳过澄清状态机
- 如果 session 正处于待澄清状态，则根据控制语义和 runtime stage 路由到不同恢复分支

分支目标包括：

- `clarification_passthrough`
- `clarification_confirm_switch`
- `clarification_current_topic`
- `clarification_new_topic`
- `clarification_freeform_router`

### 5.6 澄清恢复分支

位置：

- [server/app/workflows/chat_graph_clarification.py](server/app/workflows/chat_graph_clarification.py)

几个主要节点：

- `clarification_confirm_switch`
  - 用户确认切题后，恢复到上一轮待确认问题
- `clarification_current_topic`
  - 用户明确表示继续原主线，继续追问
- `clarification_new_topic`
  - 用户明确表示切到新主题
- `clarification_freeform_router`
  - 用户没有明确控制指令时，按 freeform 文本做二次分类
- `clarification_freeform_current_topic`
  - 认为仍然是原主线追问
- `clarification_freeform_new_topic`
  - 认为已形成新主题
- `clarification_freeform_defer`
  - 还不够明确，继续交给 `intent_guard`

### 5.7 `intent_guard`

位置：

- [server/app/workflows/chat_graph_clarification.py](server/app/workflows/chat_graph_clarification.py)
- [server/app/workflows/chat_graph_support.py](server/app/workflows/chat_graph_support.py)

作用：

- 检测当前问题是否偏离会话主线
- 决定是否先返回澄清提示，而不是直接检索

核心判断依据：

- `current_goal`
- 当前问题文本
- 文本 bigram 相似度
- 去掉“需要什么材料 / 怎么申请 / 流程 / 条件”等模板词后的主题核心差异

阈值常量定义在：

- `_INTENT_GUARD_MIN_SIMILARITY`
- `_INTENT_GUARD_MIN_FOCUS_SIMILARITY`
- `_INTENT_GUARD_MIN_TEXT_LENGTH`

位置：

- [server/app/workflows/chat_graph_support.py](server/app/workflows/chat_graph_support.py)

若判定漂移，会设置：

- `fallback_reason = "intent_clarification_required"`
- `clarification_type`
- `clarification_stage`
- `clarification_expected_input`
- `clarification_reason`
- `citations = []`
- `retrieval_count = 0`

### 5.8 `retrieve_context`

位置：

- [server/app/workflows/chat_graph_execution.py](server/app/workflows/chat_graph_execution.py)
- [server/app/services/retrieval.py](server/app/services/retrieval.py)

作用：

- 单知识库时调用 `RetrievalService.retrieve()`
- 多知识库时调用 `RetrievalService.retrieve_many()`
- 将命中的片段转成 `ChatCitation`
- 记录 `retrieval_count`
- 追加检索 trace

当前检索策略：

- Qdrant vector store
- llamaindex router retriever
- lexical rerank

### 5.9 `review_gate`

位置：

- [server/app/workflows/chat_graph_execution.py](server/app/workflows/chat_graph_execution.py)

作用：

- 如果 assistant 没开启 `review_enabled`，直接跳过
- 如果当前没有 citations，也直接跳过 review
- 如果命中 `review_rules`，则设置：
  - `fallback_reason = "review_required"`
  - `review_reason = ...`

### 5.10 `review_hold`

位置：

- [server/app/workflows/chat_graph_execution.py](server/app/workflows/chat_graph_execution.py)

作用：

- 当 `fallback_reason == "review_required"` 时调用 `interrupt(...)`
- 挂起 workflow，等待人工审核恢复

这就是 review 能够在后面通过 `Command(resume=...)` 恢复的根因。

## 6. `_stream_or_fallback_answer()` 的五条输出路径

位置：

- [server/app/api/routes/chat.py](server/app/api/routes/chat.py)

它根据 `PreparedWorkflowData` 决定最终输出。

### 路径 A：无知识库

条件：

- `fallback_reason == "no_knowledge_base_selected"`

行为：

- 调用 `build_no_knowledge_base_answer()`
- 用 `_iter_text_chunk_events()` 把整段文本按固定 chunk 大小伪流式输出

代码：

- [server/app/api/routes/chat.py](server/app/api/routes/chat.py)
- [server/app/services/answer_generation.py](server/app/services/answer_generation.py)

### 路径 B：命中 review

条件：

- `fallback_reason == "review_required"`

行为：

- 直接调用 `build_review_required_answer()`
- 仍然按文本切片形式流式输出

注意：

- 此时不是模型流式输出
- 是路由层直接返回一段“需要人工复核”的说明文本

### 路径 C：需要澄清

条件：

- `fallback_reason == "intent_clarification_required"`

行为：

- 调用 `build_intent_clarification_answer()`
- 返回澄清文本

### 路径 D：检索无命中

条件：

- `prepared_context.citations` 为空

行为：

- 调用 `build_no_retrieval_hits_answer()`
- 返回无命中兜底文本

### 路径 E：正常模型流式生成

条件：

- 有 citations
- 没有触发 fallback

行为：

- 创建 `AnswerGenerationService()`
- 调用 `stream_answer()`
- 每得到一个 `chunk.delta`，立即发一个 SSE `chunk`

相关代码：

- [server/app/api/routes/chat.py](server/app/api/routes/chat.py)
- [server/app/services/answer_generation.py](server/app/services/answer_generation.py)

## 7. 模型流式生成链路

### 7.1 `AnswerGenerationService.stream_answer()`

位置：

- [server/app/services/answer_generation.py](server/app/services/answer_generation.py)

作用：

- 校验必须有 citations
- 调用 `build_messages()` 组装 prompt
- 遍历候选模型
- 通过 `ChatModelService.stream()` 获取上游流
- 把每个上游 chunk 包装为 `AnswerGenerationChunk`
- 最终聚合完整文本，返回 `GeneratedAnswer`

### 7.2 Prompt 组成

位置：

- [server/app/services/answer_generation.py](server/app/services/answer_generation.py)

`build_messages()` 里会把这些上下文放进 prompt：

- assistant 名称
- system prompt
- `question`
- `effective_question`
- `current_goal`
- `memory_summary`
- 知识库范围
- citation 片段上下文

因此实际大模型看到的问题不是只有“用户原始问题”，而是一个拼好的完整上下文。

## 8. SSE 事件格式

事件格式定义在：

- [server/app/api/routes/chat.py](server/app/api/routes/chat.py)

核心函数：

```python
def _format_sse_event(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
```

本链路里会出现的事件：

- `start`
- `chunk`
- `completed`
- `error`

其中：

- `start`：上下文准备完成
- `chunk`：增量文本
- `completed`：整轮问答最终完成
- `error`：模型不可用、生成失败或其他异常

## 9. 落库与运行态更新

### 9.1 user message 何时写入

在 workflow 执行前，通过 `_start_turn()` 就已经落库。

位置：

- [server/app/services/chat_rag.py](server/app/services/chat_rag.py)
- [server/app/repositories/messages.py](server/app/repositories/messages.py)

### 9.2 assistant message 何时写入

只有 `_stream_or_fallback_answer()` 完整结束后，才会执行 `finalize_turn()` 正式落 assistant 消息。

位置：

- [server/app/services/chat_rag.py](server/app/services/chat_rag.py)

正常路径：

- `persist_assistant_message()`

review 路径：

- `finalize_review_hold()`
- 先落一条 assistant pending message
- 再创建 review task

### 9.3 session 运行态如何更新

更新入口：

- [server/app/services/chat_rag.py](server/app/services/chat_rag.py)
- [server/app/repositories/sessions.py](server/app/repositories/sessions.py)

生命周期规则：

- [server/app/services/workflow_runtime.py](server/app/services/workflow_runtime.py)

主要状态：

- 普通完成：`active / completed`
- 待澄清：`awaiting_clarification / waiting_clarification_*`
- 待审核：`awaiting_review / waiting_review`

### 9.4 audit log

写审计日志的位置：

- [server/app/services/audit_logs.py](server/app/services/audit_logs.py)

普通问答或澄清：

- `log_chat_result()`

命中 review：

- `log_review_pending()`

review 恢复后：

- `log_review_decision()`

## 10. review 中断后的恢复链路

这部分不在 `event_stream` 里继续执行，但它和 `event_stream` 的链路是同一条 workflow thread。

恢复入口：

- [server/app/services/review_tasks.py](server/app/services/review_tasks.py)

主链路：

1. `ReviewTaskService.approve()` 或 `reject()`
2. 调用 `_resume_workflow()`
3. 根据 review_task 里的 `workflow_thread_id` 执行：

```python
workflow.invoke(
    Command(
        resume={
            "action": action,
            "reviewer_note": reviewer_note,
            "manual_answer": manual_answer,
        }
    ),
    config={"configurable": {"thread_id": workflow_thread_id}},
)
```

4. workflow 从 `review_hold` 继续恢复
5. 审核通过：
   - 继续到 `compose_answer`
6. 审核驳回：
   - 直接生成人工处理结论
7. 用 `_update_pending_message()` 回写之前那条 pending assistant 消息

相关代码：

- [server/app/services/review_tasks.py](server/app/services/review_tasks.py)
- [server/app/workflows/chat_graph_execution.py](server/app/workflows/chat_graph_execution.py)

## 11. 一张顺序图式总结

```text
HTTP /sessions/{id}/chat/stream
  -> stream_session_chat()
  -> event_stream()
  -> SessionChatService.prepare_stream_context()
  -> _invoke_workflow()
     -> _load_recent_messages()
     -> _start_turn() 写 user message
     -> build_chat_workflow(include_compose_answer=False)
     -> assistant_config
     -> kb_scope
     -> question_intake
     -> memory_manager
     -> clarification_router / clarification handlers
     -> intent_guard
     -> retrieve_context
     -> review_gate
     -> review_hold(可能 interrupt)
  -> PreparedWorkflowData
  -> SSE start
  -> _stream_or_fallback_answer()
     -> fallback 文本切片输出
        or
     -> AnswerGenerationService.stream_answer()
        -> ChatModelService.stream()
        -> SSE chunk*
  -> finalize_turn()
     -> 写 assistant message
     -> 更新 session runtime
     -> 写 audit log
     -> 如命中 review 则创建 review task
  -> SSE completed
```

## 12. 推荐断点位置

如果你要单步调试，建议按下面顺序打断点：

- `stream_session_chat()`：
  [server/app/api/routes/chat.py](server/app/api/routes/chat.py)
- `event_stream()`：
  [server/app/api/routes/chat.py](server/app/api/routes/chat.py)
- `_invoke_workflow()`：
  [server/app/services/chat_rag.py](server/app/services/chat_rag.py)
- `memory_manager`：
  [server/app/workflows/chat_graph_clarification.py](server/app/workflows/chat_graph_clarification.py)
- `intent_guard`：
  [server/app/workflows/chat_graph_clarification.py](server/app/workflows/chat_graph_clarification.py)
- `retrieve_context`：
  [server/app/workflows/chat_graph_execution.py](server/app/workflows/chat_graph_execution.py)
- `_stream_or_fallback_answer()`：
  [server/app/api/routes/chat.py](server/app/api/routes/chat.py)
- `finalize_turn()`：
  [server/app/services/chat_rag.py](server/app/services/chat_rag.py)

## 13. 最容易混淆的几个点

- `event_stream` 本身只是 SSE 包装层，不负责做检索决策和意图判断。
- LangGraph 在当前流式接口里只负责准备上下文，不负责真正的 token streaming。
- `workflow_thread_id` 复用了本轮 user message 的 `message_id`。
- review 命中后，流式接口返回的是“进入人工复核”的提示文本，不是挂起等待前端继续收流。
- assistant 消息不是边流边落库，而是在整轮流式结束后统一落库。
- 澄清和 review 的核心运行态会写入 `sessions` 表，用于下一轮恢复。
