<template>
  <div class="page-grid">
    <el-card shadow="never">
      <template #header>
        <div class="page-card__header">
          <span>会话设置</span>
          <el-button text @click="refreshAll">刷新</el-button>
        </div>
      </template>

      <el-skeleton v-if="bootstrapping" :rows="4" animated />
      <el-alert v-else-if="bootError" type="error" :title="bootError" show-icon />
      <div v-else class="chat-settings">
        <el-alert
          v-if="assistants.length === 0"
          type="warning"
          title="暂无助理，请先创建助理。"
          show-icon
          :closable="false"
        />
        <template v-else>
          <el-form label-position="top" @submit.prevent>
            <el-form-item label="新建会话">
              <div class="chat-settings__row">
                <el-select
                  v-model="newSessionAssistantId"
                  placeholder="请选择助理"
                  style="width: 260px"
                >
                  <el-option
                    v-for="assistant in assistants"
                    :key="assistant.assistant_id"
                    :label="assistant.assistant_name"
                    :value="assistant.assistant_id"
                  />
                </el-select>
                <el-button
                  type="primary"
                  :loading="creatingSession"
                  @click="handleCreateSession"
                >
                  新建会话
                </el-button>
              </div>
            </el-form-item>
            <el-form-item label="当前会话">
              <el-select
                v-model="selectedSessionId"
                placeholder="请选择会话"
                style="width: 100%"
                @change="handleSessionChange"
              >
                <el-option
                  v-for="session in sessions"
                  :key="session.session_id"
                  :label="`${session.title} · ${session.assistant_name}`"
                  :value="session.session_id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="知识库范围（可多选）">
              <el-select
                v-model="selectedKnowledgeBaseIds"
                multiple
                collapse-tags
                collapse-tags-tooltip
                clearable
                placeholder="未选择时使用助理默认知识库"
                style="width: 100%"
              >
                <el-option
                  v-for="item in knowledgeBases"
                  :key="item.knowledge_base_id"
                  :label="item.knowledge_base_name"
                  :value="item.knowledge_base_id"
                />
              </el-select>
            </el-form-item>
          </el-form>
        </template>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <span>会话消息</span>
      </template>

      <el-skeleton v-if="loadingMessages" :rows="6" animated />
      <el-alert v-else-if="messageError" type="error" :title="messageError" show-icon />
      <el-empty
        v-else-if="!selectedSessionId && !streaming"
        description="请选择会话。"
      />
      <el-empty
        v-else-if="messages.length === 0 && !streaming"
        description="暂无消息，开始提问即可。"
      />
      <div v-else class="message-list">
        <div
          v-if="
            latestSelectedKbIds.length > 0 ||
            latestWorkflowTrace.length > 0 ||
            latestFallbackReason ||
            latestReviewId
          "
          class="trace-panel"
        >
          <div class="trace-panel__title">本轮执行信息</div>
          <div class="trace-summary">
            <span>
              检索命中数：{{ latestRetrievalCount }}
              <template v-if="latestSelectedKbIds.length > 0">
                · 知识库范围：{{ latestSelectedKbIds.join("、") }}
              </template>
            </span>
            <el-button
              text
              class="trace-summary__toggle"
              @click="tracePanelExpanded = !tracePanelExpanded"
            >
              {{ tracePanelExpanded ? "收起" : "查看详情" }}
            </el-button>
          </div>
          <template v-if="tracePanelExpanded">
            <div v-if="latestFallbackReason" class="trace-panel__row">
            兜底原因：{{ latestFallbackReason }}
            </div>
            <div v-if="latestReviewId" class="trace-panel__row">
              审核任务：{{ latestReviewId }}（{{ latestReviewStatus || "pending" }}）
            </div>
            <div v-if="latestWorkflowTrace.length > 0" class="trace-panel__steps">
              <div
                v-for="(step, index) in latestWorkflowTrace"
                :key="`${step.node}-${index}`"
                class="trace-step"
              >
                <div class="trace-step__node">{{ step.node }}</div>
                <div class="trace-step__detail">{{ step.detail }}</div>
              </div>
            </div>
          </template>
        </div>

        <div
          v-for="message in messages"
          :key="message.message_id"
          class="message-item"
          :class="`message-item--${message.role}`"
        >
          <div class="message-item__meta">
            <el-tag :type="message.role === 'assistant' ? 'success' : 'info'">
              {{ message.role === "assistant" ? "助理" : "用户" }}
            </el-tag>
            <span>{{ formatDateTime(message.created_at) }}</span>
          </div>
          <div
            class="message-item__content markdown-body"
            v-html="renderMarkdown(message.content)"
          ></div>
          <div
            v-if="message.citations.length > 0"
            class="message-item__citations"
          >
            <div class="citation-summary">
              <span>引用片段 {{ message.citations.length }} 条</span>
              <el-button
                text
                class="citation-summary__toggle"
                @click="toggleMessageCitations(message.message_id)"
              >
                {{ isMessageCitationsExpanded(message.message_id) ? "收起" : "查看引用" }}
              </el-button>
            </div>
            <div
              v-if="isMessageCitationsExpanded(message.message_id)"
              v-for="citation in message.citations"
              :key="citation.chunk_id"
              class="citation-card"
            >
              <div class="citation-card__meta">
                {{ citation.file_name }} · 分块 {{ citation.chunk_index + 1 }} ·
                相似度 {{ citation.score.toFixed(3) }}
              </div>
              <div class="citation-card__content">{{ citation.content }}</div>
            </div>
          </div>
        </div>

        <div
          v-if="streaming"
          class="message-item message-item--user"
        >
          <div class="message-item__meta">
            <el-tag type="info">用户</el-tag>
            <span>正在发送</span>
          </div>
          <div class="message-item__content">{{ streamingQuestion }}</div>
        </div>

        <div
          v-if="streaming"
          class="message-item message-item--assistant"
        >
          <div class="message-item__meta">
            <el-tag type="success">助理</el-tag>
            <span>正在生成</span>
          </div>
          <div
            class="message-item__content markdown-body"
            v-html="renderMarkdown(streamingAnswer || '正在整理检索结果...')"
          ></div>
          <div
            v-if="streamingCitations.length > 0"
            class="message-item__citations"
          >
            <div class="citation-summary">
              <span>引用片段 {{ streamingCitations.length }} 条</span>
              <el-button
                text
                class="citation-summary__toggle"
                @click="streamingCitationsExpanded = !streamingCitationsExpanded"
              >
                {{ streamingCitationsExpanded ? "收起" : "查看引用" }}
              </el-button>
            </div>
            <div
              v-if="streamingCitationsExpanded"
              v-for="citation in streamingCitations"
              :key="citation.chunk_id"
              class="citation-card"
            >
              <div class="citation-card__meta">
                {{ citation.file_name }} · 分块 {{ citation.chunk_index + 1 }} ·
                相似度 {{ citation.score.toFixed(3) }}
              </div>
              <div class="citation-card__content">{{ citation.content }}</div>
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <span>发送问题</span>
      </template>

      <el-form label-position="top" @submit.prevent>
        <el-form-item label="问题内容">
          <el-input
            v-model="question"
            type="textarea"
            :rows="4"
            placeholder="请输入问题"
          />
        </el-form-item>
        <div class="chat-actions">
          <el-button
            type="primary"
            :loading="sending"
            :disabled="streaming"
            @click="handleSendQuestion"
          >
            发送并流式检索
          </el-button>
          <el-button
            v-if="streaming"
            @click="handleStopStreaming"
          >
            停止生成
          </el-button>
        </div>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from "element-plus";
import MarkdownIt from "markdown-it";
import { onBeforeUnmount, onMounted, ref } from "vue";

import { fetchAssistants, type AssistantSummary } from "@/api/assistants";
import {
  fetchSessionMessages,
  streamSessionChat,
  type ChatCitation,
  type ChatQueryResponse,
  type MessageSummary,
} from "@/api/chat";
import {
  fetchKnowledgeBases,
  type KnowledgeBaseSummary,
} from "@/api/knowledgeBases";
import { fetchReviewTask, type ReviewTaskDetail } from "@/api/reviews";
import {
  createSession,
  fetchSessions,
  type SessionSummary,
} from "@/api/sessions";
import { formatDateTime } from "@/utils/display";

const assistants = ref<AssistantSummary[]>([]);
const sessions = ref<SessionSummary[]>([]);
const knowledgeBases = ref<KnowledgeBaseSummary[]>([]);
const messages = ref<MessageSummary[]>([]);
const bootstrapping = ref(false);
const bootError = ref<string | null>(null);
const loadingMessages = ref(false);
const messageError = ref<string | null>(null);
const creatingSession = ref(false);
const sending = ref(false);
const streaming = ref(false);
const newSessionAssistantId = ref("");
const selectedSessionId = ref("");
const selectedKnowledgeBaseIds = ref<string[]>([]);
const question = ref("");
const streamingQuestion = ref("");
const streamingAnswer = ref("");
const streamingCitations = ref<ChatCitation[]>([]);
const streamingCitationsExpanded = ref(false);
const latestSelectedKbIds = ref<string[]>([]);
const latestRetrievalCount = ref(0);
const latestFallbackReason = ref("");
const latestReviewId = ref("");
const latestReviewStatus = ref("");
const latestWorkflowTrace = ref<ChatQueryResponse["workflow_trace"]>([]);
const tracePanelExpanded = ref(false);
const expandedMessageCitations = ref<Record<string, boolean>>({});
let reviewPollingTimer: ReturnType<typeof setInterval> | null = null;
let reviewPollingInFlight = false;
let currentPollingReviewId = "";
let lastResolvedReviewId = "";
let streamAbortController: AbortController | null = null;

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
});

function escapeHtml(raw: string): string {
  return raw
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderMarkdown(content: string): string {
  try {
    return markdown.render(content ?? "");
  } catch (error) {
    console.warn("markdown render failed", error);
    return `<p>${escapeHtml(content ?? "")}</p>`;
  }
}

function resetChatMeta() {
  latestSelectedKbIds.value = [];
  latestRetrievalCount.value = 0;
  latestFallbackReason.value = "";
  latestReviewId.value = "";
  latestReviewStatus.value = "";
  latestWorkflowTrace.value = [];
  tracePanelExpanded.value = false;
}

function applyChatMeta(payload: ChatQueryResponse) {
  latestSelectedKbIds.value = payload.selected_kb_ids;
  latestRetrievalCount.value = payload.retrieval_count;
  latestFallbackReason.value = payload.fallback_reason ?? "";
  latestReviewId.value = payload.review_id ?? "";
  latestReviewStatus.value = payload.review_status ?? "";
  latestWorkflowTrace.value = payload.workflow_trace;
}

function applyReviewTaskMeta(reviewTask: ReviewTaskDetail) {
  latestSelectedKbIds.value = reviewTask.selected_kb_ids;
  latestRetrievalCount.value = reviewTask.retrieval_count;
  latestFallbackReason.value = reviewTask.status === "pending" ? "review_required" : "";
  latestReviewId.value = reviewTask.review_id;
  latestReviewStatus.value = reviewTask.status;
  latestWorkflowTrace.value = reviewTask.workflow_trace;
}

function isMessageCitationsExpanded(messageId: string): boolean {
  return Boolean(expandedMessageCitations.value[messageId]);
}

function toggleMessageCitations(messageId: string) {
  expandedMessageCitations.value = {
    ...expandedMessageCitations.value,
    [messageId]: !expandedMessageCitations.value[messageId],
  };
}

function stopReviewPolling() {
  if (reviewPollingTimer !== null) {
    clearInterval(reviewPollingTimer);
    reviewPollingTimer = null;
  }
  currentPollingReviewId = "";
}

async function pollReviewStatus(reviewId: string) {
  if (!selectedSessionId.value || reviewPollingInFlight) {
    return;
  }

  reviewPollingInFlight = true;
  try {
    const reviewTask = await fetchReviewTask(reviewId);
    applyReviewTaskMeta(reviewTask);
    if (reviewTask.status === "pending") {
      return;
    }

    stopReviewPolling();
    await Promise.all([loadBootstrapData(), loadMessages()]);
    if (lastResolvedReviewId !== reviewTask.review_id) {
      if (reviewTask.status === "approved") {
        ElMessage.success("审核已通过，聊天消息已自动更新。");
      } else if (reviewTask.status === "rejected") {
        ElMessage.info("审核已驳回，聊天消息已更新为人工结论。");
      }
      lastResolvedReviewId = reviewTask.review_id;
    }
  } catch (error) {
    console.warn("review polling failed", error);
  } finally {
    reviewPollingInFlight = false;
  }
}

function startReviewPolling(reviewId: string) {
  if (!reviewId) {
    stopReviewPolling();
    return;
  }
  if (reviewPollingTimer !== null && currentPollingReviewId === reviewId) {
    return;
  }
  stopReviewPolling();
  currentPollingReviewId = reviewId;
  reviewPollingTimer = setInterval(() => {
    void pollReviewStatus(reviewId);
  }, 5000);
}

function selectedSessionSummary(): SessionSummary | undefined {
  return sessions.value.find((item) => item.session_id === selectedSessionId.value);
}

async function syncPendingReviewMeta() {
  const session = selectedSessionSummary();
  const pendingReviewId = session?.workflow_runtime?.pending_review_id ?? "";
  if (!pendingReviewId) {
    stopReviewPolling();
    return;
  }

  try {
    const reviewTask = await fetchReviewTask(pendingReviewId);
    applyReviewTaskMeta(reviewTask);
    if (reviewTask.status === "pending") {
      startReviewPolling(reviewTask.review_id);
    } else {
      stopReviewPolling();
    }
  } catch (error) {
    console.warn("sync pending review meta failed", error);
  }
}

async function loadBootstrapData() {
  bootstrapping.value = true;
  bootError.value = null;
  try {
    const [assistantData, sessionData, knowledgeBaseData] = await Promise.all([
      fetchAssistants(),
      fetchSessions(),
      fetchKnowledgeBases(),
    ]);
    assistants.value = assistantData;
    sessions.value = sessionData;
    knowledgeBases.value = knowledgeBaseData;
    selectedKnowledgeBaseIds.value = selectedKnowledgeBaseIds.value.filter((item) =>
      knowledgeBases.value.some((kb) => kb.knowledge_base_id === item),
    );

    if (!newSessionAssistantId.value && assistants.value.length > 0) {
      newSessionAssistantId.value = assistants.value[0].assistant_id;
    }
    if (
      sessions.value.length > 0 &&
      !sessions.value.some((item) => item.session_id === selectedSessionId.value)
    ) {
      selectedSessionId.value = sessions.value[0].session_id;
    }
  } catch (error) {
    bootError.value = error instanceof Error ? error.message : "聊天页初始化失败。";
  } finally {
    bootstrapping.value = false;
  }
}

async function loadMessages() {
  messageError.value = null;
  if (!selectedSessionId.value) {
    messages.value = [];
    return;
  }

  loadingMessages.value = true;
  try {
    messages.value = await fetchSessionMessages(selectedSessionId.value);
  } catch (error) {
    messageError.value = error instanceof Error ? error.message : "消息列表加载失败。";
  } finally {
    loadingMessages.value = false;
  }
}

async function refreshAll() {
  await loadBootstrapData();
  await loadMessages();
  await syncPendingReviewMeta();
}

async function handleSessionChange() {
  resetChatMeta();
  stopReviewPolling();
  await loadMessages();
  await syncPendingReviewMeta();
}

async function handleCreateSession() {
  if (!newSessionAssistantId.value) {
    ElMessage.warning("请先选择助理。");
    return;
  }

  creatingSession.value = true;
  try {
    const session = await createSession({
      assistant_id: newSessionAssistantId.value,
      title: "",
    });
    await loadBootstrapData();
    selectedSessionId.value = session.session_id;
    resetChatMeta();
    await loadMessages();
    ElMessage.success("会话创建成功。");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "会话创建失败。");
  } finally {
    creatingSession.value = false;
  }
}

async function handleSendQuestion() {
  if (!selectedSessionId.value) {
    ElMessage.warning("请先创建或选择一个会话。");
    return;
  }
  if (!question.value.trim()) {
    ElMessage.warning("请输入问题内容。");
    return;
  }

  const currentQuestion = question.value.trim();
  sending.value = true;
  streaming.value = true;
  streamingQuestion.value = currentQuestion;
  streamingAnswer.value = "";
  streamingCitations.value = [];
  streamingCitationsExpanded.value = false;
  resetChatMeta();
  streamAbortController = new AbortController();

  try {
    question.value = "";
    await streamSessionChat(
      selectedSessionId.value,
      {
        question: currentQuestion,
        knowledge_base_ids: selectedKnowledgeBaseIds.value,
        top_k: 4,
      },
      {
        onStart: (payload) => {
          latestSelectedKbIds.value = payload.selected_kb_ids;
          latestRetrievalCount.value = payload.retrieval_count;
        },
        onChunk: (payload) => {
          streamingAnswer.value += payload.delta;
        },
        onCompleted: (payload) => {
          streamingAnswer.value = payload.answer;
          streamingCitations.value = payload.citations;
          applyChatMeta(payload);
          if (payload.review_id) {
            startReviewPolling(payload.review_id);
            ElMessage.info("该问题已进入审核台，审核通过后会更新本轮回复。");
          }
        },
        onError: (payload) => {
          throw new Error(payload.message);
        },
      },
      streamAbortController.signal,
    );
    await Promise.all([loadBootstrapData(), loadMessages()]);
  } catch (error) {
    if (streamAbortController?.signal.aborted) {
      ElMessage.info("已停止生成。");
      await Promise.all([loadBootstrapData(), loadMessages()]);
    } else {
      ElMessage.error(error instanceof Error ? error.message : "提问失败。");
    }
  } finally {
    sending.value = false;
    streaming.value = false;
    streamingQuestion.value = "";
    streamingAnswer.value = "";
    streamingCitations.value = [];
    streamingCitationsExpanded.value = false;
    streamAbortController = null;
  }
}

function handleStopStreaming() {
  streamAbortController?.abort();
}

onMounted(async () => {
  await refreshAll();
});

onBeforeUnmount(() => {
  stopReviewPolling();
});
</script>

<style scoped>
.page-grid {
  display: grid;
  gap: 20px;
}

.page-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.chat-settings {
  display: grid;
  gap: 16px;
}

.chat-settings__row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.message-list {
  display: grid;
  gap: 16px;
}

.message-item {
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 16px;
  display: grid;
  gap: 12px;
}

.message-item--assistant {
  background: #f0fdf4;
}

.message-item--user {
  background: #f8fafc;
}

.message-item__meta {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #6b7280;
  font-size: 13px;
}

.message-item__content {
  line-height: 1.7;
}

.markdown-body :deep(p) {
  margin: 0 0 12px;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0 0 12px;
  padding-left: 22px;
}

.markdown-body :deep(li + li) {
  margin-top: 6px;
}

.markdown-body :deep(strong) {
  font-weight: 700;
}

.markdown-body :deep(code) {
  background: rgba(15, 23, 42, 0.06);
  border-radius: 6px;
  padding: 2px 6px;
  font-size: 0.92em;
}

.markdown-body :deep(pre) {
  margin: 0 0 12px;
  background: #111827;
  color: #f9fafb;
  padding: 12px;
  border-radius: 10px;
  overflow-x: auto;
}

.markdown-body :deep(pre code) {
  background: transparent;
  padding: 0;
  color: inherit;
}

.markdown-body :deep(blockquote) {
  margin: 0 0 12px;
  padding-left: 12px;
  border-left: 4px solid #bbf7d0;
  color: #374151;
}

.markdown-body :deep(a) {
  color: #2563eb;
  text-decoration: none;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

.message-item__citations {
  display: grid;
  gap: 10px;
}

.citation-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #6b7280;
  font-size: 13px;
}

.citation-summary__toggle {
  padding: 0;
}

.citation-card {
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid #d1d5db;
  padding: 12px;
  display: grid;
  gap: 8px;
}

.citation-card__meta {
  color: #6b7280;
  font-size: 12px;
}

.citation-card__content {
  white-space: pre-wrap;
  line-height: 1.6;
  color: #111827;
}

.trace-panel {
  border: 1px solid #dbeafe;
  background: #eff6ff;
  border-radius: 12px;
  padding: 14px;
  display: grid;
  gap: 10px;
}

.trace-panel__title {
  font-weight: 600;
  color: #1d4ed8;
}

.trace-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #1f2937;
  line-height: 1.6;
}

.trace-summary__toggle {
  padding: 0;
}

.trace-panel__row {
  color: #1f2937;
  line-height: 1.6;
}

.trace-panel__steps {
  display: grid;
  gap: 8px;
}

.trace-step {
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid #bfdbfe;
  padding: 10px 12px;
  display: grid;
  gap: 4px;
}

.trace-step__node {
  font-size: 12px;
  color: #1d4ed8;
  font-weight: 600;
}

.trace-step__detail {
  line-height: 1.6;
  color: #1f2937;
}

.chat-actions {
  display: flex;
  gap: 12px;
}
</style>
