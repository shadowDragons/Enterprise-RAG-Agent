# LangGraph 问答工作流完整细节

本文展开说明 `build_chat_workflow()` 组装出来的问答工作流。

主入口：

- [server/app/workflows/chat_graph.py](server/app/workflows/chat_graph.py)

核心节点实现：

- 澄清、记忆、意图守卫：[server/app/workflows/chat_graph_clarification.py](server/app/workflows/chat_graph_clarification.py)
- 检索、审核、答案生成：[server/app/workflows/chat_graph_execution.py](server/app/workflows/chat_graph_execution.py)
- 状态定义与辅助函数：[server/app/workflows/chat_graph_support.py](server/app/workflows/chat_graph_support.py)

外层调用位置：

- [server/app/services/chat_rag.py](server/app/services/chat_rag.py)

## 1. 这条工作流解决什么问题

这条 LangGraph workflow 不是单纯的“问一句、检索、回答”。

它实际处理的是企业 RAG 问答里的完整决策链：

```text
加载助理配置
-> 选择知识库范围
-> 解析用户输入中的控制语义
-> 整理历史记忆和当前会话目标
-> 如果上一轮处于待澄清状态，则先恢复澄清状态机
-> 判断当前问题是否偏离会话主线
-> 检索知识库
-> 判断是否命中人工复核规则
-> 必要时 interrupt 挂起
-> 可选生成最终答案
```

所以它既包含 RAG 检索，也包含多轮会话控制、意图漂移检测、人工审核中断和恢复。

## 2. 工作流的入口输入

工作流不是直接接收 HTTP payload，而是由 `SessionChatService._build_workflow_input()` 组装初始 state。

位置：

- [server/app/services/chat_rag.py](server/app/services/chat_rag.py)

初始 state 包含：

| 字段 | 来源 | 含义 |
| --- | --- | --- |
| `assistant_id` | assistant | 助理 ID |
| `assistant_name` | assistant | 助理名称 |
| `assistant_config` | assistant | 助理运行配置，包括 system prompt、默认模型、默认知识库、review 规则 |
| `session_status` | session.status | 当前会话状态，如 `active`、`awaiting_clarification`、`awaiting_review` |
| `session_runtime_context` | session runtime 字段整理 | 上一轮遗留的澄清上下文，如 `current_goal`、`pending_question` |
| `session_runtime_state` | session.runtime_state | 当前运行态，如 `waiting_clarification_switch` |
| `question` | 当前用户输入 | 本轮用户问题，已经在 `_start_turn()` 中 `strip()` |
| `requested_knowledge_base_ids` | 请求参数 | 本轮用户显式指定的知识库 ID 列表 |
| `message_history` | 最近消息 | 当前轮之前的历史消息窗口 |
| `top_k` | 请求参数 | 检索返回条数 |
| `review_interrupt_enabled` | 固定 True | 命中审核规则时是否允许 `interrupt()` |

注意：

- `_invoke_workflow()` 会先读取历史消息，再写入本轮 user message，然后才执行 `workflow.invoke()`。
- 因此 `message_history` 不包含当前这条 user message。
- 当前 user message 的 `message_id` 会作为 `workflow_thread_id`，传给 LangGraph config 的 `thread_id`。

相关代码：

- `_start_turn()`：[server/app/services/chat_rag.py](server/app/services/chat_rag.py)
- `_invoke_workflow()`：[server/app/services/chat_rag.py](server/app/services/chat_rag.py)
- `_build_workflow_config()`：[server/app/services/chat_rag.py](server/app/services/chat_rag.py)

## 3. State 类型结构

工作流的 state 类型是 `ChatWorkflowState`。

位置：

- [server/app/workflows/chat_graph_support.py](server/app/workflows/chat_graph_support.py)

它是一个 `TypedDict(total=False)`，意味着字段可以逐步补齐，节点只返回自己要更新的一部分字段。

主要字段分组如下。

### 3.1 助理配置

| 字段 | 含义 |
| --- | --- |
| `assistant_id` | 助理 ID |
| `assistant_name` | 助理名称 |
| `assistant_config` | 助理完整运行配置 |

`assistant_config` 内部包含：

| 字段 | 含义 |
| --- | --- |
| `assistant_id` | 助理 ID |
| `assistant_name` | 助理名称 |
| `system_prompt` | 助理 system prompt |
| `default_model` | 默认模型 |
| `default_kb_ids` | 默认知识库 ID 列表 |
| `review_rules` | 人工复核规则 |
| `review_enabled` | 是否启用 review gate |

### 3.2 会话运行态

| 字段 | 含义 |
| --- | --- |
| `session_status` | 会话状态 |
| `session_runtime_context` | 上一轮持久化的运行上下文 |
| `session_runtime_state` | 上一轮持久化的运行态 |

### 3.3 问题处理

| 字段 | 含义 |
| --- | --- |
| `question` | 本轮原始问题，来自外层输入 |
| `raw_question` | `_intake_question` 保存的原始问题 |
| `normalized_question` | 去掉控制前缀后的问题 |
| `question_control_action` | 控制动作，如 `explicit_switch`、`confirm_switch` |
| `resolved_question` | 本轮最终要处理的问题 |
| `effective_question` | 实际用于检索的问题，可能包含历史上下文 |
| `current_goal` | 当前会话主线或目标 |
| `memory_summary` | 最近历史消息摘要 |

### 3.4 澄清状态

| 字段 | 含义 |
| --- | --- |
| `clarification_route` | `clarification_router` 选出的路由 |
| `clarification_action` | 澄清处理动作 |
| `clarification_freeform_route` | freeform 澄清分类路由 |
| `clarification_type` | 澄清类型 |
| `clarification_stage` | 澄清阶段 |
| `clarification_expected_input` | 下一轮期望用户输入类型 |
| `clarification_reason` | 澄清原因 |

### 3.5 意图守卫

| 字段 | 含义 |
| --- | --- |
| `intent_action` | `continue`、`clarify`、`switch_topic` 等 |
| `intent_drift_score` | 意图漂移分数，通常是 `1 - similarity` |

### 3.6 检索与审核

| 字段 | 含义 |
| --- | --- |
| `requested_knowledge_base_ids` | 用户显式选择的知识库 |
| `selected_knowledge_base_id` | 最终选中的主知识库 |
| `selected_kb_ids` | 最终选中的知识库列表 |
| `top_k` | 检索条数 |
| `citations` | 检索命中的引用片段 |
| `retrieval_count` | 命中数量 |
| `review_interrupt_enabled` | 是否允许 review interrupt |
| `review_reason` | 命中审核规则的原因 |
| `review_decision` | 人工审核结果 |

### 3.7 结果与追踪

| 字段 | 含义 |
| --- | --- |
| `answer` | 最终答案 |
| `fallback_reason` | 兜底原因，如 `no_knowledge_base_selected` |
| `workflow_trace` | 工作流节点执行说明列表 |

## 4. `build_chat_workflow()` 的组装逻辑

入口：

- [server/app/workflows/chat_graph.py](server/app/workflows/chat_graph.py)

函数签名：

```python
def build_chat_workflow(
    *,
    include_compose_answer: bool,
    checkpointer=None,
):
```

参数含义：

| 参数 | 含义 |
| --- | --- |
| `include_compose_answer` | 是否把 `compose_answer` 节点放进图里 |
| `checkpointer` | LangGraph checkpoint 后端，用于 interrupt / resume |

核心行为：

1. 创建 `StateGraph(ChatWorkflowState)`。
2. 注册固定节点 `_WORKFLOW_NODES`。
3. 如果 `include_compose_answer=True`，额外注册 `compose_answer`。
4. 添加普通边。
5. 添加条件边。
6. 使用 `builder.compile(checkpointer=checkpointer)` 编译成可执行 workflow。

## 5. `include_compose_answer` 的意义

这是理解这条图最重要的开关。

### 5.1 `include_compose_answer=False`

这是当前 SSE 流式接口的用法。

位置：

- [server/app/services/chat_rag.py](server/app/services/chat_rag.py)

行为：

- graph 只跑到上下文准备阶段。
- 它会完成知识库范围选择、问题归一化、记忆整理、澄清判断、意图守卫、检索、review 判断。
- 它不会在 graph 内部生成最终答案。
- 如果某个条件本来应该进入 `compose_answer`，这里会直接 `END`。

为什么这样设计：

- 流式接口需要由路由层调用 `AnswerGenerationService.stream_answer()`，把 token 作为 SSE chunk 发给前端。
- 如果 graph 内部调用 `_compose_answer()`，那是同步生成完整答案，不适合当前流式输出。

### 5.2 `include_compose_answer=True`

这是完整工作流或 review 恢复时会用到的模式。

行为：

- graph 会注册 `compose_answer` 节点。
- fallback、无命中、澄清、正常问答都可以在 graph 内部产出 `answer`。
- review `interrupt()` 恢复后，如果审核通过，可以继续进入 `compose_answer`。

## 6. 总体拓扑

代码里的主干边：

```text
START
-> assistant_config
-> kb_scope
-> question_intake
-> memory_manager
-> clarification_router
-> 条件进入 clarification 分支
-> 条件进入 intent_guard / retrieve_context / compose_answer / END
-> retrieve_context
-> review_gate
-> 条件进入 review_hold / compose_answer / END
-> review_hold
-> 条件进入 compose_answer / END
-> compose_answer
-> END
```

更完整地展开：

```text
START
  -> assistant_config
  -> kb_scope
  -> question_intake
  -> memory_manager
  -> clarification_router
      -> clarification_passthrough
      -> clarification_confirm_switch
      -> clarification_current_topic
      -> clarification_new_topic
      -> clarification_freeform_router
          -> clarification_freeform_current_topic
          -> clarification_freeform_new_topic
          -> clarification_freeform_defer
  -> intent_guard
  -> retrieve_context
  -> review_gate
      -> review_hold
  -> compose_answer（可选）
  -> END
```

## 7. 节点 1：`assistant_config`

实现：

- `_load_assistant_config()`
- [server/app/workflows/chat_graph_clarification.py](server/app/workflows/chat_graph_clarification.py)

输入依赖：

| 字段 | 用途 |
| --- | --- |
| `assistant_config` | 读取 assistant ID、名称、默认知识库 |

处理逻辑：

1. 读取 `state["assistant_config"]`。
2. 从 `assistant_config.default_kb_ids` 中过滤空值。
3. 返回助理 ID、助理名称。
4. 初始化 `selected_kb_ids=[]`。
5. 追加一条 `workflow_trace`，说明已加载助理配置和默认知识库数量。

输出字段：

| 字段 | 值 |
| --- | --- |
| `assistant_id` | `assistant_config["assistant_id"]` |
| `assistant_name` | `assistant_config["assistant_name"]` |
| `selected_kb_ids` | 空列表 |
| `workflow_trace` | 增加 `assistant_config` 节点 trace |

下一步：

```text
assistant_config -> kb_scope
```

这是固定边。

## 8. 节点 2：`kb_scope`

实现：

- `_resolve_kb_scope()`
- [server/app/workflows/chat_graph_clarification.py](server/app/workflows/chat_graph_clarification.py)

输入依赖：

| 字段 | 用途 |
| --- | --- |
| `requested_knowledge_base_ids` | 用户本轮显式选择的知识库 |
| `assistant_config.default_kb_ids` | 助理默认知识库 |
| `settings.max_chat_selected_kb_count` | 最多允许选择的知识库数量 |

处理逻辑：

1. 清洗用户显式传入的知识库 ID。
2. 使用 `dict.fromkeys(...)` 去重并保持顺序。
3. 读取 assistant 默认知识库，过滤空值。
4. 如果用户显式选择了知识库，优先使用用户选择。
5. 如果用户未选择，则使用 assistant 默认知识库。
6. 根据 `settings.max_chat_selected_kb_count` 截断。
7. 第一个知识库作为 `selected_knowledge_base_id`。
8. 完整列表作为 `selected_kb_ids`。

有知识库时输出：

| 字段 | 值 |
| --- | --- |
| `selected_knowledge_base_id` | `selected_kb_ids[0]` |
| `selected_kb_ids` | 选中的知识库 ID 列表 |
| `workflow_trace` | 说明使用用户显式选择或默认知识库 |

无知识库时输出：

| 字段 | 值 |
| --- | --- |
| `selected_knowledge_base_id` | 空字符串 |
| `selected_kb_ids` | 空列表 |
| `citations` | 空列表 |
| `retrieval_count` | 0 |
| `fallback_reason` | `no_knowledge_base_selected` |
| `workflow_trace` | 说明当前没有可用知识库 |

注意：

- `kb_scope` 即使设置了 `fallback_reason=no_knowledge_base_selected`，图的固定边仍然会继续进入 `question_intake`。
- 后续路由会根据是否有 `selected_knowledge_base_id` 和是否允许 `compose_answer` 决定结束或生成兜底。

下一步：

```text
kb_scope -> question_intake
```

这是固定边。

## 9. 节点 3：`question_intake`

实现：

- `_intake_question()`
- [server/app/workflows/chat_graph_clarification.py](server/app/workflows/chat_graph_clarification.py)

输入依赖：

| 字段 | 用途 |
| --- | --- |
| `question` | 原始用户输入 |
| `session_status` | 判断是否处于待澄清状态 |

输出目标：

- 保留用户原话为 `raw_question`
- 提取真正问题为 `normalized_question`
- 标记控制动作 `question_control_action`

初始值：

```python
raw_question = state["question"].strip()
normalized_question = raw_question
control_action = ""
```

### 9.1 session 处于 `awaiting_clarification`

当 `session_status == "awaiting_clarification"` 时，会识别更多控制语义。

#### 9.1.1 继续当前话题前缀

判断函数：

- `_looks_like_stay_on_current_topic()`

前缀集合：

- `继续当前话题`
- `继续原话题`
- `继续这个话题`
- `继续刚才的话题`
- `不换话题`
- `不切换话题`
- `先不切换`
- `不切换`

命中后：

| 字段 | 值 |
| --- | --- |
| `question_control_action` | `continue_current_topic` |
| `normalized_question` | 去掉前缀后的问题 |

例如：

```text
输入：继续当前话题：请假最晚什么时候提
raw_question：继续当前话题：请假最晚什么时候提
normalized_question：请假最晚什么时候提
question_control_action：continue_current_topic
```

#### 9.1.2 拒绝切题并继续原话题

判断函数：

- `_extract_clarification_continuation_question()`

它先识别拒绝切题前缀：

- `不是`
- `不切换`
- `不用切换`
- `先不切换`
- `别切换`
- `不换话题`

然后继续剥离填充语：

- `我是想继续问`
- `我想继续问`
- `我是想问`
- `我想问`
- `继续当前话题`
- `继续原话题`
- `继续这个话题`
- `继续问`

命中后：

| 字段 | 值 |
| --- | --- |
| `question_control_action` | `reject_switch` |
| `normalized_question` | 提取出的原话题追问 |

例如：

```text
输入：不是，我是想继续问审批需要多久
raw_question：不是，我是想继续问审批需要多久
normalized_question：审批需要多久
question_control_action：reject_switch
```

#### 9.1.3 确认继续原话题

判断函数：

- `_looks_like_continue_current_topic_confirmation()`

确认词集合：

- `继续`
- `继续吧`
- `继续当前话题`
- `继续原话题`
- `继续这个话题`
- `按原话题`
- `还是原话题`
- `就原话题`

命中后：

| 字段 | 值 |
| --- | --- |
| `question_control_action` | `continue_current_topic` |
| `normalized_question` | 空字符串 |

这表示用户只表达了“继续”，但没有补充具体问题。

#### 9.1.4 确认切换主题

判断函数：

- `_looks_like_switch_confirmation()`

确认词集合：

- `是`
- `是的`
- `对`
- `对的`
- `嗯`
- `好的`
- `好`
- `行`
- `确认`
- `确认切换`
- `切换`
- `切换吧`
- `换吧`

命中后：

| 字段 | 值 |
| --- | --- |
| `question_control_action` | `confirm_switch` |
| `normalized_question` | 空字符串 |

这表示用户确认切换到上一轮 pending 的问题。

#### 9.1.5 显式切换到新问题

判断函数：

- `_looks_like_explicit_topic_switch()`

前缀集合：

- `切换到新问题`
- `换一个问题`
- `换个问题`
- `另一个问题`
- `切换话题`
- `切换到`
- `新问题`
- `新话题`
- `另外问`

命中后：

| 字段 | 值 |
| --- | --- |
| `question_control_action` | `explicit_switch` |
| `normalized_question` | 去掉切题前缀后的新问题 |

### 9.2 session 不处于 `awaiting_clarification`

普通状态下，只识别显式切题。

如果输入以 `_TOPIC_SWITCH_PREFIXES` 开头：

| 字段 | 值 |
| --- | --- |
| `question_control_action` | `explicit_switch` |
| `normalized_question` | 去掉切题前缀后的新问题 |

除此之外，保持：

| 字段 | 值 |
| --- | --- |
| `question_control_action` | 空字符串 |
| `normalized_question` | 原始问题 |

### 9.3 输出字段

| 字段 | 含义 |
| --- | --- |
| `raw_question` | 原始用户输入 |
| `normalized_question` | 控制语义剥离后的问题 |
| `question_control_action` | 控制动作 |
| `workflow_trace` | 本节点 trace |

下一步：

```text
question_intake -> memory_manager
```

这是固定边。

## 10. 节点 4：`memory_manager`

实现：

- `_manage_memory()`
- [server/app/workflows/chat_graph_clarification.py](server/app/workflows/chat_graph_clarification.py)

输入依赖：

| 字段 | 用途 |
| --- | --- |
| `message_history` | 最近历史消息 |
| `raw_question` | 原始输入 |
| `normalized_question` | 归一化问题 |
| `session_status` | 是否处于待澄清 |
| `session_runtime_context` | 澄清恢复上下文 |
| `settings.chat_memory_message_window` | 历史窗口大小 |

处理步骤：

1. 过滤历史消息中的空 content。
2. 截取最近 `settings.chat_memory_message_window` 条。
3. 读取 `raw_question`。
4. 读取 `question = normalized_question`，没有则退回 `raw_question`。
5. 调用 `_resolve_current_goal()` 推断当前会话主线。
6. 调用 `_build_memory_summary()` 构造历史摘要。
7. 如果 `question` 非空，调用 `_resolve_effective_question()` 得到检索问题。
8. 写入 trace。

### 10.1 `current_goal` 怎么来

函数：

- `_resolve_current_goal()`
- [server/app/workflows/chat_graph_support.py](server/app/workflows/chat_graph_support.py)

逻辑：

```text
如果 session_status == awaiting_clarification：
  优先用 session_runtime_context.current_goal
  如果没有，就用当前 question
否则：
  取历史里的最后一条 user 消息
  如果没有历史 user 消息，就用当前 question
```

注意：

- 当前实现会把上一条非空 user 消息当作会话主线。
- 如果上一条是“好的”“谢谢”等低信息文本，也可能被当作 `current_goal`。
- 后续 `intent_guard` 对过短文本有兜底，不会轻易触发漂移澄清，但检索改写仍可能受到影响。

### 10.2 `memory_summary` 怎么来

函数：

- `_build_memory_summary()`

逻辑：

- 如果没有历史，返回空字符串。
- 取历史最后 4 条。
- 用户消息标记为 `用户`。
- 非用户消息标记为 `助手`。
- 换行替换为空格。
- 每条最多保留 80 字，超出加 `...`。
- 用换行拼接。

### 10.3 `effective_question` 怎么来

函数：

- `_resolve_effective_question()`

逻辑：

```text
如果没有历史：
  返回当前 question
如果当前 question 不像追问：
  返回当前 question
如果 current_goal == question：
  返回当前 question
否则：
  返回 "上一轮问题：{current_goal}\n当前追问：{question}"
```

`_looks_like_follow_up()` 判断追问的规则：

- 长度小于等于 12，认为像追问。
- 或者以这些词开头：
  - `那`
  - `那么`
  - `这个`
  - `这个问题`
  - `它`
  - `还`
  - `还有`
  - `另外`
  - `再`
  - `然后`
  - `继续`
  - `补充`
  - `那如果`
  - `那报销`
  - `那请假`

### 10.4 输出字段

| 字段 | 含义 |
| --- | --- |
| `current_goal` | 当前会话目标 |
| `resolved_question` | 本轮问题，来自 `normalized_question` |
| `memory_summary` | 历史摘要 |
| `effective_question` | 检索使用的问题 |
| `workflow_trace` | 本节点 trace |

特殊情况：

- 如果本轮用户只输入控制指令，例如 `继续当前话题`，`question` 可能为空。
- 此时 `effective_question` 为空，trace 会说明“当前输入主要是控制指令，等待澄清恢复节点决定下一步”。

下一步：

```text
memory_manager -> clarification_router
```

这是固定边。

## 11. 节点 5：`clarification_router`

实现：

- `_clarification_router()`
- [server/app/workflows/chat_graph_clarification.py](server/app/workflows/chat_graph_clarification.py)

输入依赖：

| 字段 | 用途 |
| --- | --- |
| `session_status` | 判断是否进入澄清恢复状态机 |
| `question_control_action` | 用户本轮控制动作 |
| `session_runtime_state` | 推断上一轮澄清阶段 |
| `session_runtime_context.clarification_stage` | 推断上一轮澄清阶段 |
| `clarification_stage` | 当前 state 中已有的澄清阶段 |

### 11.1 非待澄清状态

如果：

```text
session_status != "awaiting_clarification"
```

输出：

| 字段 | 值 |
| --- | --- |
| `clarification_route` | `clarification_passthrough` |
| `workflow_trace` | 说明跳过澄清状态机 |

下一步：

```text
clarification_router -> clarification_passthrough
```

### 11.2 待澄清状态

如果会话处于 `awaiting_clarification`，就要恢复上一轮挂起的澄清状态。

路由优先级如下。

#### 优先级 1：继续原话题或拒绝切题

条件：

```text
question_control_action in {"continue_current_topic", "reject_switch"}
```

路由：

```text
clarification_current_topic
```

#### 优先级 2：显式切新主题，或上一轮正在等待新主题问题

条件：

```text
question_control_action == "explicit_switch"
or clarification_stage == "collect_new_topic_question"
```

路由：

```text
clarification_new_topic
```

#### 优先级 3：确认切题，或上一轮处于确认切题阶段

条件：

```text
question_control_action == "confirm_switch"
or clarification_stage == "confirm_switch"
```

路由：

```text
clarification_confirm_switch
```

#### 默认：freeform 澄清分类

如果上面都没命中：

```text
clarification_freeform_router
```

### 11.3 `clarification_stage` 的解析方式

函数：

- `_resolve_clarification_stage()`

优先级：

1. 先从 `session_runtime_state` 转换。
2. 再从 `session_runtime_context.clarification_stage` 读取。
3. 再从当前 state 的 `clarification_stage` 读取。
4. 都没有时默认为 `confirm_switch`。

`session_runtime_state` 到 stage 的转换：

| runtime_state | clarification_stage |
| --- | --- |
| `waiting_new_topic_question` | `collect_new_topic_question` |
| `waiting_clarification_question` | `collect_current_topic_question` |
| `waiting_clarification_switch` | `confirm_switch` |

## 12. 节点 6：`clarification_passthrough`

实现：

- `_clarification_passthrough()`

用途：

- 表示当前会话不是待澄清状态，澄清状态机直接跳过。

输出：

| 字段 | 值 |
| --- | --- |
| `clarification_action` | `skip` |

后续路由由 `_route_after_clarification_handler()` 决定。

由于 `clarification_action="skip"` 不属于恢复动作，也没有 fallback，因此会进入：

```text
intent_guard
```

## 13. 节点 7：`clarification_confirm_switch`

实现：

- `_clarification_confirm_switch()`

输入依赖：

| 字段 | 用途 |
| --- | --- |
| `message_history` | 当前函数传入但实际未使用 |
| `session_status` | 判断是否可取 pending question |
| `session_runtime_context.pending_question` | 上一轮待确认的新问题 |
| `question_control_action` | 是否为 `confirm_switch` |

处理逻辑：

1. 通过 `_resolve_pending_question()` 取 `pending_question`。
2. 只有在 `session_status == "awaiting_clarification"` 时才会返回 pending question。
3. 如果 `pending_question` 存在，并且用户本轮 `question_control_action == "confirm_switch"`，就恢复这个 pending question。
4. 否则不直接处理，返回 `defer_to_clarification_freeform`。

成功恢复时输出：

| 字段 | 值 |
| --- | --- |
| `current_goal` | `pending_question` |
| `resolved_question` | `pending_question` |
| `effective_question` | `pending_question` |
| `clarification_action` | `resume_pending_topic` |
| `intent_action` | `switch_topic` |
| `intent_drift_score` | 0.0 |
| `workflow_trace` | 说明用户确认切换主题 |

未恢复时输出：

| 字段 | 值 |
| --- | --- |
| `clarification_action` | `defer_to_clarification_freeform` |

后续：

- 成功恢复后，如果有知识库，进入 `retrieve_context`。
- 未恢复时，进入 `clarification_freeform_router`。

## 14. 节点 8：`clarification_current_topic`

实现：

- `_clarification_current_topic()`

场景：

- 用户在上一轮待澄清后，本轮表达“继续原话题”或“不是切题”。

输入依赖：

| 字段 | 用途 |
| --- | --- |
| `raw_question` | 原始用户输入 |
| `normalized_question` | 提取出的具体追问 |
| `current_goal` | 原会话主线 |
| `message_history` | 判断追问时改写检索问题 |
| `question_control_action` | 区分继续当前话题和拒绝切题 |

### 14.1 用户说继续原话题，并且带了具体问题

条件：

```text
question_control_action == "continue_current_topic"
and question 非空
```

调用：

```python
_build_current_topic_follow_up_resolution(...)
```

输出：

| 字段 | 值 |
| --- | --- |
| `current_goal` | 当前具体问题 |
| `resolved_question` | 当前具体问题 |
| `effective_question` | 当前具体问题，或“上一轮问题 + 当前追问” |
| `clarification_action` | `resume_current_topic` |
| `intent_action` | `continue` |
| `intent_drift_score` | 0.0 |
| `workflow_trace` | 说明恢复原主线 |

### 14.2 用户说继续原话题，但没给具体问题

条件：

```text
question_control_action == "continue_current_topic"
and question 为空
```

调用：

```python
_build_continue_current_topic_clarification(...)
```

输出：

| 字段 | 值 |
| --- | --- |
| `current_goal` | 原主线 |
| `resolved_question` | 空字符串 |
| `effective_question` | 空字符串 |
| `clarification_action` | `wait_for_follow_up_question` |
| `clarification_type` | `continue_current_topic` |
| `clarification_stage` | `collect_current_topic_question` |
| `clarification_expected_input` | `follow_up_question` |
| `clarification_reason` | 用户表示继续原主线，但未给出具体追问 |
| `intent_action` | `clarify` |
| `intent_drift_score` | 0.0 |
| `fallback_reason` | `intent_clarification_required` |
| `citations` | 空列表 |
| `retrieval_count` | 0 |

### 14.3 用户拒绝切题，并且带了具体问题

条件：

```text
question_control_action == "reject_switch"
and question 非空
```

输出与 14.1 类似，仍然是恢复原主线。

### 14.4 用户拒绝切题，但没给具体问题

条件：

```text
question_control_action == "reject_switch"
and question 为空
```

输出与 14.2 类似，继续等待用户补充具体追问。

后续：

- 恢复成功：进入 `retrieve_context` 或 `compose_answer` 或 `END`。
- 仍需澄清：进入 `compose_answer` 或 `END`。

## 15. 节点 9：`clarification_new_topic`

实现：

- `_clarification_new_topic()`

场景：

- 用户明确想切换到新主题。
- 或上一轮已经等待用户补充新主题问题。

输入依赖：

| 字段 | 用途 |
| --- | --- |
| `raw_question` | 原始输入 |
| `normalized_question` | 提取出的新问题 |
| `current_goal` | 当前目标 |
| `clarification_stage` | 是否为 `collect_new_topic_question` |

### 15.1 上一轮已经在等待新主题问题，本轮给了具体问题

条件：

```text
clarification_stage == "collect_new_topic_question"
and question 非空
```

输出：

| 字段 | 值 |
| --- | --- |
| `current_goal` | 当前问题 |
| `resolved_question` | 当前问题 |
| `effective_question` | 当前问题 |
| `clarification_action` | `switch_to_new_topic` |
| `intent_action` | `switch_topic` |
| `intent_drift_score` | 0.0 |
| `workflow_trace` | 说明按新主题继续 |

### 15.2 上一轮等待新主题问题，本轮仍然没有具体问题

条件：

```text
clarification_stage == "collect_new_topic_question"
and question 为空
```

调用：

```python
_build_new_topic_question_clarification(...)
```

输出：

| 字段 | 值 |
| --- | --- |
| `current_goal` | 原目标 |
| `resolved_question` | 空字符串 |
| `effective_question` | 空字符串 |
| `clarification_action` | `wait_for_new_topic_question` |
| `clarification_type` | `new_topic_question` |
| `clarification_stage` | `collect_new_topic_question` |
| `clarification_expected_input` | `new_topic_question` |
| `clarification_reason` | 用户要切换主题，但未给出新问题 |
| `intent_action` | `clarify` |
| `fallback_reason` | `intent_clarification_required` |
| `citations` | 空列表 |
| `retrieval_count` | 0 |

### 15.3 本轮明确切换主题，但没有具体问题

条件：

```text
clarification_stage != "collect_new_topic_question"
and question 为空
```

输出与 15.2 类似，继续等待新主题问题。

### 15.4 本轮明确给出了新主题问题

条件：

```text
question 非空
```

输出：

| 字段 | 值 |
| --- | --- |
| `current_goal` | 新问题 |
| `resolved_question` | 新问题 |
| `effective_question` | 新问题 |
| `clarification_action` | `switch_to_new_topic` |
| `intent_action` | `switch_topic` |
| `intent_drift_score` | 0.0 |

后续：

- 有知识库：进入 `retrieve_context`。
- 无知识库且 `include_compose_answer=True`：进入 `compose_answer`。
- 无知识库且 `include_compose_answer=False`：结束。

## 16. 节点 10：`clarification_freeform_router`

实现：

- `_clarification_freeform_router()`

场景：

- session 处于待澄清状态。
- 用户本轮没有明确说“继续”“切换”“确认”等控制指令。
- 需要根据自然语言判断它更像原主线追问还是新主题。

输入依赖：

| 字段 | 用途 |
| --- | --- |
| `raw_question` | 原始输入 |
| `normalized_question` | 当前问题 |
| `current_goal` | 原主线 |

### 16.1 明显上下文依赖追问

判断函数：

- `_looks_like_context_dependent_follow_up()`

判断规则：

- 以追问词开头，如 `那`、`这个`、`它`、`还有`、`继续`。
- 或包含 `这个`、`那个`、`上述`、`上面`、`刚才`、`前面`、`这件事`。

命中后：

| 字段 | 值 |
| --- | --- |
| `clarification_freeform_route` | `clarification_freeform_current_topic` |

### 16.2 文本足够长，做相似度分析

条件：

```text
len(normalized_question) >= _INTENT_GUARD_MIN_TEXT_LENGTH
and len(normalized_goal) >= _INTENT_GUARD_MIN_TEXT_LENGTH
```

这里的长度不是原始字符长度，而是 `_normalize_intent_text()` 后的长度。

相似度函数：

- `_analyze_intent_similarity(current_goal, question)`

它返回：

| 返回值 | 含义 |
| --- | --- |
| `similarity` | 当前问题和主线的 bigram Jaccard 相似度 |
| `focus_similarity` | 去掉模板词后的主题核心相似度 |
| `goal_focus` | 原主线主题核心 |
| `question_focus` | 当前问题主题核心 |
| `template_overlap_drift` | 是否“模板相似但主题核心不同” |

如果：

```text
similarity < _INTENT_GUARD_MIN_SIMILARITY
or template_overlap_drift
```

路由到：

```text
clarification_freeform_new_topic
```

否则路由到：

```text
clarification_freeform_current_topic
```

### 16.3 文本不够判断

如果当前问题和目标都不满足最小长度，则输出：

| 字段 | 值 |
| --- | --- |
| `clarification_freeform_route` | `clarification_freeform_defer` |

表示交给 `intent_guard` 做最后判断。

## 17. 节点 11：`clarification_freeform_current_topic`

实现：

- `_clarification_freeform_current_topic()`

场景：

- freeform 输入被判断为继续原主线。

处理逻辑：

1. 如果当前问题像上下文依赖追问，调用 `_build_current_topic_follow_up_resolution()`。
2. 否则计算当前问题和原主线的相似度。
3. 把当前问题直接作为本轮 `current_goal`、`resolved_question`、`effective_question`。

输出字段：

| 字段 | 值 |
| --- | --- |
| `current_goal` | 当前问题 |
| `resolved_question` | 当前问题 |
| `effective_question` | 当前问题，或上下文改写后的问题 |
| `clarification_action` | `resume_current_topic` |
| `intent_action` | `continue` |
| `intent_drift_score` | `1.0 - similarity` 或 0.0 |
| `workflow_trace` | 说明恢复原主线 |

## 18. 节点 12：`clarification_freeform_new_topic`

实现：

- `_clarification_freeform_new_topic()`

场景：

- freeform 输入被判断为新主题。

处理逻辑：

1. 计算当前问题和原主线的相似度。
2. 如果是模板相似但主题核心不同，会把 `goal_focus`、`question_focus`、`focus_similarity` 写入 trace。
3. 把当前问题作为新的会话主线和检索问题。

输出字段：

| 字段 | 值 |
| --- | --- |
| `current_goal` | 当前问题 |
| `resolved_question` | 当前问题 |
| `effective_question` | 当前问题 |
| `clarification_action` | `switch_to_new_topic` |
| `intent_action` | `switch_topic` |
| `intent_drift_score` | `1.0 - similarity` |
| `workflow_trace` | 说明按新主题继续 |

## 19. 节点 13：`clarification_freeform_defer`

实现：

- `_clarification_freeform_defer()`

用途：

- freeform 文本还不足以直接恢复原话题或切新主题。
- 把决策交给后面的 `intent_guard`。

输出：

| 字段 | 值 |
| --- | --- |
| `clarification_action` | `defer_to_intent_guard` |
| `workflow_trace` | 说明继续交给意图守卫判断 |

注意：

- `_route_after_clarification_handler()` 对 `defer_to_intent_guard` 没有特殊 return。
- 它最终会走默认分支 `intent_guard`。

## 20. 澄清分支后的统一路由

实现：

- `_route_after_clarification_handler()`

所有这些节点都会用同一个路由函数：

- `clarification_passthrough`
- `clarification_confirm_switch`
- `clarification_current_topic`
- `clarification_new_topic`
- `clarification_freeform_current_topic`
- `clarification_freeform_new_topic`
- `clarification_freeform_defer`

路由规则如下。

### 20.1 需要进入 freeform router

条件：

```text
clarification_action == "defer_to_clarification_freeform"
```

下一步：

```text
clarification_freeform_router
```

主要来自：

- `clarification_confirm_switch` 没拿到可恢复的 pending question。

### 20.2 已经需要澄清

条件：

```text
fallback_reason == "intent_clarification_required"
```

下一步：

| include_compose_answer | 下一步 |
| --- | --- |
| True | `compose_answer` |
| False | `END` |

### 20.3 已经恢复出一个可执行问题

条件：

```text
clarification_action in {
  "resume_current_topic",
  "resume_pending_topic",
  "switch_to_new_topic",
}
```

下一步：

| 条件 | 下一步 |
| --- | --- |
| 有 `selected_knowledge_base_id` | `retrieve_context` |
| 无知识库且 `include_compose_answer=True` | `compose_answer` |
| 无知识库且 `include_compose_answer=False` | `END` |

### 20.4 默认

其他情况：

```text
intent_guard
```

典型情况：

- `clarification_passthrough`
- `clarification_freeform_defer`

## 21. 节点 14：`intent_guard`

实现：

- `_intent_guard()`

用途：

- 在真正检索前，判断本轮问题是否偏离当前会话主线。
- 如果偏离明显，先返回澄清提示，而不是直接检索。

输入依赖：

| 字段 | 用途 |
| --- | --- |
| `raw_question` | 原始输入 |
| `normalized_question` | 归一化问题 |
| `current_goal` | 当前会话主线 |
| `message_history` | 判断是否有历史 |
| `question_control_action` | 显式切题时绕过漂移判断 |

### 21.1 显式切题

条件：

```text
question_control_action == "explicit_switch"
```

如果 `normalized_question` 为空：

- 调用 `_build_new_topic_question_clarification()`
- 设置 `fallback_reason=intent_clarification_required`
- 等待用户补充新主题问题

如果 `normalized_question` 非空：

输出：

| 字段 | 值 |
| --- | --- |
| `current_goal` | 新问题 |
| `resolved_question` | 新问题 |
| `effective_question` | 新问题 |
| `intent_action` | `switch_topic` |
| `intent_drift_score` | 0.0 |

这种情况下不会做相似度判断，因为用户已经明确说要切换。

### 21.2 没有足够历史或当前目标等于当前问题

条件：

```text
not history or current_goal == question
```

输出：

| 字段 | 值 |
| --- | --- |
| `intent_action` | `continue` |
| `intent_drift_score` | 0.0 |

含义：

- 没有可比较的主线。
- 或本轮问题本身就是主线。
- 跳过漂移检测。

### 21.3 当前问题明显是上下文依赖追问

条件：

```text
_looks_like_context_dependent_follow_up(question)
```

输出：

| 字段 | 值 |
| --- | --- |
| `intent_action` | `continue` |
| `intent_drift_score` | 0.0 |

原因：

- 这种问题通常需要沿当前主线理解。
- 例如：`那需要什么材料？`、`这个流程谁审批？`

### 21.4 当前问题或主线太短

条件：

```text
len(_normalize_intent_text(question)) < _INTENT_GUARD_MIN_TEXT_LENGTH
or len(_normalize_intent_text(current_goal)) < _INTENT_GUARD_MIN_TEXT_LENGTH
```

其中：

```text
_INTENT_GUARD_MIN_TEXT_LENGTH = 6
```

输出：

| 字段 | 值 |
| --- | --- |
| `intent_action` | `continue` |
| `intent_drift_score` | 0.0 |

原因：

- 文本太短时，相似度不稳定。
- 不触发澄清，避免误伤。

### 21.5 相似度与主题核心漂移判断

调用：

```python
_analyze_intent_similarity(current_goal, question)
```

内部步骤：

1. `_normalize_intent_text()` 去掉标点和空白，只保留字母、数字、中文，并转小写。
2. `_extract_bigrams()` 提取 bigram。
3. `_calculate_text_similarity()` 计算 Jaccard 相似度。
4. `_extract_intent_focus_text()` 去掉通用问句模板。
5. 再计算主题核心相似度。
6. 判断是否 `template_overlap_drift`。

通用模板词包括：

- `需要什么材料`
- `需要哪些材料`
- `怎么申请`
- `申请流程`
- `审批流程`
- `材料`
- `条件`
- `流程`
- `要求`
- `怎么`
- `如何`
- `什么`
- `哪些`
- 以及一批常见低区分度词

阈值：

| 常量 | 值 | 含义 |
| --- | --- | --- |
| `_INTENT_GUARD_MIN_SIMILARITY` | 0.18 | 整体相似度最低阈值 |
| `_INTENT_GUARD_MIN_FOCUS_SIMILARITY` | 0.18 | 主题核心相似度最低阈值 |
| `_INTENT_GUARD_MIN_TEXT_LENGTH` | 6 | 最小文本长度 |

触发漂移的条件：

```text
similarity < 0.18
or template_overlap_drift == True
```

`template_overlap_drift` 的条件：

```text
similarity >= 0.18
and focus_similarity < 0.18
and goal_focus != question_focus
```

也就是说：

- 两句话表面模板相似，例如都在问“需要什么材料”
- 但去掉模板词后，主题核心变了
- 也认为发生了漂移

### 21.6 判定漂移后的输出

输出字段：

| 字段 | 值 |
| --- | --- |
| `intent_action` | `clarify` |
| `intent_drift_score` | `1.0 - similarity` |
| `clarification_type` | `confirm_switch` |
| `clarification_stage` | `confirm_switch` |
| `clarification_expected_input` | `topic_switch_confirmation` |
| `clarification_reason` | 相关性弱或主题核心变化 |
| `fallback_reason` | `intent_clarification_required` |
| `citations` | 空列表 |
| `retrieval_count` | 0 |
| `workflow_trace` | 说明请求用户确认是否切换主题 |

### 21.7 未判定漂移后的输出

输出字段：

| 字段 | 值 |
| --- | --- |
| `intent_action` | `continue` |
| `intent_drift_score` | `1.0 - similarity` |
| `workflow_trace` | 说明继续进入检索 |

## 22. `intent_guard` 后的路由

实现：

- `_route_after_intent_guard()`

路由规则：

| 条件 | include_compose_answer | 下一步 |
| --- | --- | --- |
| `fallback_reason == intent_clarification_required` | True | `compose_answer` |
| `fallback_reason == intent_clarification_required` | False | `END` |
| 有 `selected_knowledge_base_id` | 任意 | `retrieve_context` |
| 无知识库 | True | `compose_answer` |
| 无知识库 | False | `END` |

注意：

- 如果前面的 `kb_scope` 已经设置了 `fallback_reason=no_knowledge_base_selected`，并且没有知识库，`include_compose_answer=False` 时会直接结束。
- 当前 SSE 流式接口就是 `False`，所以无知识库场景的最终兜底文案不在 graph 内生成，而在路由层 `_stream_or_fallback_answer()` 生成。

## 23. 节点 15：`retrieve_context`

实现：

- `_retrieve_context()`
- [server/app/workflows/chat_graph_execution.py](server/app/workflows/chat_graph_execution.py)

输入依赖：

| 字段 | 用途 |
| --- | --- |
| `selected_kb_ids` | 判断单知识库还是多知识库 |
| `selected_knowledge_base_id` | 单知识库检索 ID |
| `effective_question` | 优先作为检索 query |
| `resolved_question` | `effective_question` 不存在时兜底 |
| `question` | 最终兜底 query |
| `top_k` | 检索返回条数 |

### 23.1 选择检索函数

内部调用 `_retrieve_citation_dicts()`。

如果：

```text
len(selected_kb_ids) <= 1
```

调用：

```python
RetrievalService.retrieve(
    knowledge_base_id=selected_knowledge_base_id,
    query=effective_question or resolved_question or question,
    top_k=top_k,
)
```

如果是多知识库：

```python
RetrievalService.retrieve_many(
    knowledge_base_ids=selected_kb_ids,
    query=effective_question or resolved_question or question,
    top_k=top_k,
    per_kb_top_k=settings.retrieval_per_kb_top_k,
)
```

### 23.2 结果转换

检索服务返回 dict 列表后：

```python
citations = [ChatCitation(**item) for item in citation_dicts]
```

然后计算：

```python
retrieval_count = len(citations)
```

### 23.3 trace 内容

`_build_retrieval_trace_detail()` 会记录：

- 知识库范围
- 命中片段数量
- 检索策略描述
- 最高分
- 如果 `effective_question != resolved_question`，记录实际检索问题

输出字段：

| 字段 | 值 |
| --- | --- |
| `citations` | 检索命中的引用片段 |
| `retrieval_count` | 命中数量 |
| `workflow_trace` | 检索 trace |

下一步：

```text
retrieve_context -> review_gate
```

这是固定边。

## 24. 节点 16：`review_gate`

实现：

- `_review_gate()`
- [server/app/workflows/chat_graph_execution.py](server/app/workflows/chat_graph_execution.py)

输入依赖：

| 字段 | 用途 |
| --- | --- |
| `assistant_config.review_enabled` | 是否启用 review |
| `assistant_config.review_rules` | 审核规则 |
| `citations` | 无检索命中时跳过 review |
| `resolved_question` | 用于匹配 review 规则 |
| `question` | resolved_question 缺失时兜底 |

### 24.1 未启用 review

条件：

```text
not assistant_config.get("review_enabled", False)
```

输出：

```python
{}
```

即不改 state，不加 trace。

后续：

- 如果 `include_compose_answer=True`，进入 `compose_answer`。
- 如果 `include_compose_answer=False`，结束。

### 24.2 启用了 review，但没有 citations

条件：

```text
review_enabled == True
and not state.get("citations")
```

输出：

| 字段 | 值 |
| --- | --- |
| `workflow_trace` | 说明无检索命中，跳过人工复核 |

后续同 24.1。

### 24.3 启用了 review，并且有 citations

调用：

```python
evaluate_review_hit(
    state.get("resolved_question", state["question"]),
    list(assistant_config.get("review_rules", [])),
)
```

如果没有命中规则：

| 字段 | 值 |
| --- | --- |
| `workflow_trace` | 说明未命中人工复核规则 |

如果命中规则：

| 字段 | 值 |
| --- | --- |
| `fallback_reason` | `review_required` |
| `review_reason` | 命中原因 |
| `workflow_trace` | 说明暂停自动回答 |

## 25. `review_gate` 后的路由

实现：

- `_route_after_review_gate()`

路由规则：

| 条件 | 下一步 |
| --- | --- |
| `fallback_reason == review_required` 且 `review_interrupt_enabled=True` | `review_hold` |
| 否则 `include_compose_answer=True` | `compose_answer` |
| 否则 | `END` |

当前 `_build_workflow_input()` 固定设置：

```python
review_interrupt_enabled = True
```

所以命中 review 后通常会进入 `review_hold`。

## 26. 节点 17：`review_hold`

实现：

- `_review_hold()`
- [server/app/workflows/chat_graph_execution.py](server/app/workflows/chat_graph_execution.py)

用途：

- 真正执行 LangGraph `interrupt()`。
- 把当前工作流挂起，等待人工审核。
- 后续通过 `Command(resume=...)` 恢复。

### 26.1 没有命中 review

条件：

```text
fallback_reason != "review_required"
```

输出：

```python
{}
```

### 26.2 命中 review

调用：

```python
review_payload = interrupt({
    "type": "review_required",
    "question": resolved_question,
    "review_reason": review_reason,
    "selected_kb_ids": selected_kb_ids,
    "selected_knowledge_base_id": selected_knowledge_base_id,
    "retrieval_count": retrieval_count,
})
```

第一次执行到这里时：

- workflow 会中断。
- 外层 `workflow.invoke()` 返回结果中会带 `__interrupt__`。
- `SessionChatService._build_prepared_workflow_data()` 会把它识别成 `fallback_reason="review_required"`。

人工审核恢复时：

- `ReviewTaskService` 用同一个 `workflow_thread_id` 调用 `Command(resume={...})`。
- `interrupt()` 会返回 resume payload。
- 后续代码继续执行。

### 26.3 审核驳回

条件：

```text
action == "reject"
```

调用：

```python
build_review_rejected_answer(...)
```

输出：

| 字段 | 值 |
| --- | --- |
| `answer` | 人工答案，或根据 reviewer_note 生成的驳回文案 |
| `citations` | 空列表 |
| `review_decision` | `rejected` |
| `fallback_reason` | None |
| `workflow_trace` | 说明人工审核未通过 |

### 26.4 审核通过

默认 action 是 `approve`。

输出：

| 字段 | 值 |
| --- | --- |
| `review_decision` | `approved` |
| `fallback_reason` | None |
| `workflow_trace` | 说明人工审核已通过 |

## 27. `review_hold` 后的路由

实现：

- `_route_after_review_hold()`

规则：

| 条件 | 下一步 |
| --- | --- |
| `review_decision == approved` 且 `include_compose_answer=True` | `compose_answer` |
| 其他情况 | `END` |

含义：

- 审核通过后，如果图内包含 `compose_answer`，继续自动生成答案。
- 审核驳回后，`review_hold` 已经产生人工结论，直接结束。
- 如果 `include_compose_answer=False`，即使审核通过，也不会在这条图里生成答案。

## 28. 节点 18：`compose_answer`

实现：

- `_compose_answer()`
- [server/app/workflows/chat_graph_execution.py](server/app/workflows/chat_graph_execution.py)

这个节点只有 `include_compose_answer=True` 时才注册。

输入依赖：

| 字段 | 用途 |
| --- | --- |
| `question` | 原始问题 |
| `resolved_question` | 最终问题 |
| `citations` | 检索引用 |
| `assistant_name` | 兜底回答和模型 prompt |
| `assistant_config` | system prompt、默认模型 |
| `selected_knowledge_base_id` | 知识库范围 |
| `selected_kb_ids` | 知识库范围 |
| `fallback_reason` | 判断兜底类型 |
| `review_reason` | review 兜底说明 |

它按优先级处理以下场景。

### 28.1 无知识库

条件：

```text
fallback_reason == "no_knowledge_base_selected"
```

调用：

```python
build_no_knowledge_base_answer(...)
```

输出：

| 字段 | 值 |
| --- | --- |
| `answer` | 无知识库兜底回答 |
| `workflow_trace` | 说明未进入检索 |

### 28.2 需要意图澄清

条件：

```text
fallback_reason == "intent_clarification_required"
```

调用：

```python
build_intent_clarification_answer(...)
```

回答类型取决于 `clarification_type`：

| clarification_type | 回答内容 |
| --- | --- |
| `new_topic_question` | 让用户补充新主题具体问题 |
| `continue_current_topic` | 让用户补充原主线具体追问 |
| 其他或默认 | 让用户确认是否切换主题 |

输出：

| 字段 | 值 |
| --- | --- |
| `answer` | 澄清提示 |
| `workflow_trace` | 说明返回澄清提示 |

### 28.3 无检索命中

条件：

```text
not citations
```

调用：

```python
build_no_retrieval_hits_answer(...)
```

输出：

| 字段 | 值 |
| --- | --- |
| `answer` | 无命中兜底回答 |
| `fallback_reason` | None |
| `workflow_trace` | 说明检索为空 |

注意：

- 这条判断在 `review_required` 之前。
- 正常命中 review 时通常有 citations，因此不会被这条提前吃掉。

### 28.4 需要人工复核

条件：

```text
fallback_reason == "review_required"
```

调用：

```python
build_review_required_answer(...)
```

输出：

| 字段 | 值 |
| --- | --- |
| `answer` | 需要人工复核的提示 |
| `workflow_trace` | 说明需要人工复核 |

### 28.5 正常模型生成

条件：

- 有 citations
- 没有 fallback

调用：

```python
AnswerGenerationService.generate_answer(...)
```

传入参数包括：

- `assistant_name`
- `system_prompt`
- `question=resolved_question`
- `effective_question`
- `current_goal`
- `memory_summary`
- `citations`
- `selected_kb_ids`
- `selected_knowledge_base_id`
- `model_name=assistant_config.default_model`

输出：

| 字段 | 值 |
| --- | --- |
| `answer` | 模型生成内容 |
| `workflow_trace` | 说明使用哪个模型、哪个后端、多少引用 |
| `fallback_reason` | None |

下一步：

```text
compose_answer -> END
```

## 29. 结束后的结果收敛

工作流结束后，外层 `_build_prepared_workflow_data()` 会把 `workflow_result` 转成 `PreparedWorkflowData`。

位置：

- [server/app/services/chat_rag.py](server/app/services/chat_rag.py)

字段映射：

| PreparedWorkflowData 字段 | workflow_result 来源 |
| --- | --- |
| `resolved_question` | `resolved_question`，默认当前 question |
| `selected_knowledge_base_id` | `selected_knowledge_base_id`，默认空 |
| `selected_kb_ids` | `selected_kb_ids`，默认空列表 |
| `effective_question` | `effective_question`，默认当前 question |
| `current_goal` | `current_goal`，默认当前 question |
| `memory_summary` | `memory_summary`，默认空 |
| `intent_drift_score` | `intent_drift_score`，默认 0.0 |
| `clarification_type` | `clarification_type` |
| `clarification_stage` | `clarification_stage` |
| `clarification_expected_input` | `clarification_expected_input` |
| `clarification_reason` | `clarification_reason` |
| `review_reason` | `review_reason` |
| `citations` | `citations` |
| `retrieval_count` | `retrieval_count`，默认 citations 数量 |
| `fallback_reason` | `fallback_reason` |
| `workflow_trace` | `workflow_trace` |

特殊逻辑：

```python
if workflow_result.get("__interrupt__"):
    fallback_reason = "review_required"
```

这意味着：

- graph 在 `review_hold` 中断时，外层会把它解释成待人工复核。
- 后续 `event_stream` 会返回 review required 的提示，并创建 review task。

## 30. 当前 SSE 流式接口中的实际行为

当前 `event_stream` 使用：

```python
build_chat_workflow(include_compose_answer=False)
```

所以实际行为是：

```text
START
-> assistant_config
-> kb_scope
-> question_intake
-> memory_manager
-> clarification_router
-> clarification 分支
-> intent_guard
-> retrieve_context
-> review_gate
-> review_hold 可能 interrupt
-> END
```

然后由路由层 `_stream_or_fallback_answer()` 继续处理：

| workflow 结果 | 路由层行为 |
| --- | --- |
| `fallback_reason=no_knowledge_base_selected` | 流式返回无知识库兜底 |
| `fallback_reason=intent_clarification_required` | 流式返回澄清提示 |
| `fallback_reason=review_required` | 流式返回待审核提示 |
| `citations=[]` | 流式返回无命中兜底 |
| 有 citations 且无 fallback | 调用 `AnswerGenerationService.stream_answer()` 真正流式生成 |

这也是为什么在 SSE 接口里，`compose_answer` 是可选且默认不进入的。

## 31. 全部分支速查表

### 31.1 无知识库

```text
kb_scope 设置 fallback_reason=no_knowledge_base_selected
-> question_intake
-> memory_manager
-> clarification_router
-> clarification_passthrough
-> intent_guard
-> _route_after_intent_guard
-> END（include_compose_answer=False）
```

SSE 路由层再返回无知识库兜底。

### 31.2 普通新问题

```text
assistant_config
-> kb_scope
-> question_intake
-> memory_manager
-> clarification_passthrough
-> intent_guard
-> retrieve_context
-> review_gate
-> END（include_compose_answer=False）
```

SSE 路由层再根据 citations 调模型流式生成或返回无命中兜底。

### 31.3 追问

```text
question_intake 保持原问题
-> memory_manager 可能把 effective_question 改写为：
   上一轮问题：...
   当前追问：...
-> intent_guard 如果像上下文依赖追问，跳过漂移检测
-> retrieve_context 使用 effective_question 检索
```

### 31.4 意图漂移

```text
intent_guard 发现 similarity < 0.18
或 template_overlap_drift=True
-> 设置 fallback_reason=intent_clarification_required
-> END（include_compose_answer=False）
```

SSE 路由层返回澄清提示。

### 31.5 用户确认切换主题

前提：

- session 处于 `awaiting_clarification`
- runtime 中有 `pending_question`
- 用户输入类似 `是的`、`确认切换`

流程：

```text
question_intake -> question_control_action=confirm_switch
-> clarification_router -> clarification_confirm_switch
-> 恢复 pending_question
-> retrieve_context
```

### 31.6 用户继续原话题

前提：

- session 处于 `awaiting_clarification`
- 用户输入 `继续当前话题：...` 或 `不是，我想继续问...`

流程：

```text
question_intake -> continue_current_topic / reject_switch
-> clarification_router -> clarification_current_topic
-> 恢复原主线追问
-> retrieve_context
```

如果没有具体追问：

```text
clarification_current_topic
-> fallback_reason=intent_clarification_required
-> END
```

SSE 路由层继续提示用户补充具体问题。

### 31.7 用户切换到新主题但没给问题

```text
question_intake -> explicit_switch, normalized_question=""
-> clarification_new_topic 或 intent_guard
-> fallback_reason=intent_clarification_required
-> clarification_type=new_topic_question
-> END
```

SSE 路由层提示用户补充新主题问题。

### 31.8 命中人工审核

```text
retrieve_context 命中 citations
-> review_gate 命中 review_rules
-> fallback_reason=review_required
-> review_hold
-> interrupt(...)
```

外层识别 `__interrupt__`，返回待审核提示并创建 review task。

### 31.9 审核通过后恢复

```text
ReviewTaskService.approve()
-> Command(resume={"action": "approve", ...})
-> review_hold 返回 review_decision=approved
-> 如果 include_compose_answer=True
   -> compose_answer
   -> END
```

### 31.10 审核驳回后恢复

```text
ReviewTaskService.reject()
-> Command(resume={"action": "reject", ...})
-> review_hold 生成人工处理结论
-> END
```

## 32. 最关键的设计点

1. 节点返回的是 state patch，不是完整 state。
2. `workflow_trace` 是贯穿全链路的解释日志。
3. `kb_scope` 不直接终止工作流，而是写 `fallback_reason`，让后续路由决定怎么结束。
4. `question_intake` 只做控制语义解析，不做语义漂移判断。
5. `memory_manager` 负责把“当前问题”和“会话主线”整理出来。
6. `clarification_router` 只在 session 已经处于 `awaiting_clarification` 时真正生效。
7. `intent_guard` 是普通问答进入检索前的最后一道主线保护。
8. `retrieve_context` 只负责检索和引用转换，不负责回答。
9. `review_gate` 只决定是否需要人工复核，不执行中断。
10. `review_hold` 才是真正执行 `interrupt()` 的节点。
11. `compose_answer` 是否存在完全由 `include_compose_answer` 决定。
12. SSE 流式接口用的是 `include_compose_answer=False`，所以最终流式生成发生在 graph 外部。

