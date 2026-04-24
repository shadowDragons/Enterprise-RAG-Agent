<template>
  <div class="page-grid">
    <el-card shadow="never">
      <template #header>
        <div class="page-card__header">
          <div class="page-card__title">会话列表</div>
          <div class="page-card__actions">
            <el-select
              v-model="filterAssistantId"
              clearable
              placeholder="按助理筛选"
              style="width: 220px"
              @change="loadSessions"
            >
              <el-option
                v-for="assistant in assistants"
                :key="assistant.assistant_id"
                :label="assistant.assistant_name"
                :value="assistant.assistant_id"
              />
            </el-select>
            <el-select
              v-model="filterStatus"
              clearable
              placeholder="按状态筛选"
              style="width: 180px"
            >
              <el-option label="进行中" value="active" />
              <el-option label="等待审核" value="awaiting_review" />
              <el-option label="等待澄清" value="awaiting_clarification" />
            </el-select>
            <el-button
              type="primary"
              :disabled="assistants.length === 0"
              @click="openCreateDialog"
            >
              新建会话
            </el-button>
            <el-button text @click="loadSessions">刷新</el-button>
          </div>
        </div>
      </template>

      <el-alert
        v-if="assistants.length === 0 && !loadingAssistants"
        type="warning"
        title="暂无可用助理，请先创建助理。"
        show-icon
        :closable="false"
        class="list-alert"
      />
      <el-skeleton v-if="loadingSessions || loadingAssistants" :rows="4" animated />
      <el-alert v-else-if="error" type="error" :title="error" show-icon />
      <el-empty
        v-else-if="filteredSessions.length === 0"
        description="暂无符合条件的会话。"
      />
      <el-table v-else :data="filteredSessions" stripe>
        <el-table-column prop="title" label="标题" min-width="220" />
        <el-table-column prop="assistant_name" label="助理" min-width="180" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="运行状态" min-width="260">
          <template #default="{ row }">
            <div v-if="row.workflow_runtime" class="runtime-summary">
              <div class="runtime-summary__line">
                <el-tag size="small" :type="runtimeTagType(row.workflow_runtime.runtime_state)">
                  {{ row.workflow_runtime.runtime_label || "运行中" }}
                </el-tag>
                <span v-if="row.workflow_runtime.checkpoint_label">
                  {{ row.workflow_runtime.checkpoint_label }}
                </span>
              </div>
              <div v-if="row.workflow_runtime.latest_node" class="runtime-summary__line">
                节点：{{ row.workflow_runtime.latest_node }}
              </div>
              <div
                v-if="row.workflow_runtime.pending_review_status === 'escalated'"
                class="runtime-summary__line runtime-summary__line--danger"
              >
                审核已升级：{{ row.workflow_runtime.pending_review_escalation_reason || "超时待处理" }}
              </div>
              <div v-if="runtimeQuestion(row)" class="runtime-summary__line">
                最近问题：{{ runtimeQuestion(row) }}
              </div>
            </div>
            <span v-else class="runtime-summary runtime-summary--idle">暂无运行上下文</span>
          </template>
        </el-table-column>
        <el-table-column prop="message_count" label="消息数" width="90" />
        <el-table-column label="更新时间" min-width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="220" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button text type="primary" @click="openDetailDrawer(row)">详情</el-button>
              <el-button
                text
                type="danger"
                :loading="deletingSessionId === row.session_id"
                @click="handleDeleteSession(row)"
              >
                删除
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="createDialogVisible"
      title="新建会话"
      width="520px"
      destroy-on-close
    >
      <el-alert
        v-if="assistants.length === 0 && !loadingAssistants"
        type="warning"
        title="暂无可用助理，请先创建助理。"
        show-icon
        :closable="false"
      />

      <el-form v-else label-position="top" @submit.prevent>
        <el-form-item label="选择助理">
          <el-select
            v-model="form.assistant_id"
            placeholder="请选择助理"
            style="width: 100%"
          >
            <el-option
              v-for="assistant in assistants"
              :key="assistant.assistant_id"
              :label="assistant.assistant_name"
              :value="assistant.assistant_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="会话标题">
          <el-input v-model="form.title" placeholder="输入会话标题" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-actions">
          <el-button @click="createDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="submitSession">
            创建
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-drawer
      v-model="detailDrawerVisible"
      title="会话详情"
      size="820px"
      destroy-on-close
    >
      <div class="detail-layout">
        <el-skeleton v-if="detailLoading" :rows="8" animated />
        <el-alert
          v-else-if="detailError"
          type="error"
          :title="detailError"
          show-icon
        />
        <template v-else-if="selectedSession">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="会话标题">
              {{ selectedSession.title }}
            </el-descriptions-item>
            <el-descriptions-item label="所属助理">
              {{ selectedSession.assistant_name }}
            </el-descriptions-item>
            <el-descriptions-item label="当前状态">
              <el-tag :type="statusTagType(selectedSession.status)">
                {{ statusLabel(selectedSession.status) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="消息数">
              {{ selectedSession.message_count }}
            </el-descriptions-item>
            <el-descriptions-item label="更新时间">
              {{ formatDateTime(selectedSession.updated_at) }}
            </el-descriptions-item>
            <el-descriptions-item label="生命周期">
              {{
                selectedSession.workflow_runtime?.runtime_label ||
                "未进入特殊运行态"
              }}
            </el-descriptions-item>
            <el-descriptions-item label="等待对象">
              {{ selectedSession.workflow_runtime?.waiting_for || "无" }}
            </el-descriptions-item>
            <el-descriptions-item label="当前主线">
              {{ selectedSession.workflow_runtime?.current_goal || "无" }}
            </el-descriptions-item>
            <el-descriptions-item label="已解析问题">
              {{ selectedSession.workflow_runtime?.resolved_question || "无" }}
            </el-descriptions-item>
            <el-descriptions-item label="待确认问题">
              {{ selectedSession.workflow_runtime?.pending_question || "无" }}
            </el-descriptions-item>
            <el-descriptions-item label="澄清阶段">
              {{ selectedSession.workflow_runtime?.clarification_stage || "无" }}
            </el-descriptions-item>
            <el-descriptions-item label="待审核状态">
              {{
                selectedSession.workflow_runtime?.pending_review_status === "escalated"
                  ? "已升级"
                  : selectedSession.workflow_runtime?.pending_review_status === "pending"
                    ? "待审核"
                    : "无"
              }}
            </el-descriptions-item>
            <el-descriptions-item
              v-if="selectedSession.workflow_runtime?.pending_review_escalation_reason"
              label="升级原因"
            >
              {{ selectedSession.workflow_runtime.pending_review_escalation_reason }}
            </el-descriptions-item>
            <el-descriptions-item
              v-if="selectedSession.workflow_runtime?.pending_review_escalated_at"
              label="升级时间"
            >
              {{ formatDateTime(selectedSession.workflow_runtime.pending_review_escalated_at) }}
            </el-descriptions-item>
            <el-descriptions-item label="恢复方式">
              {{ selectedSession.workflow_runtime?.resume_strategy || "无" }}
            </el-descriptions-item>
            <el-descriptions-item label="最近节点">
              {{
                selectedSession.workflow_runtime?.latest_node
                  ? `${selectedSession.workflow_runtime.latest_node} / ${selectedSession.workflow_runtime.latest_node_detail || "-"}`
                  : "暂无"
              }}
            </el-descriptions-item>
            <el-descriptions-item label="Checkpoint">
              <div class="multiline-text">
                {{
                  selectedSession.workflow_runtime?.workflow_checkpoint_id ||
                  "暂无"
                }}
                <template v-if="selectedSession.workflow_runtime?.checkpoint_label">
                  {{ "\n" }}{{ selectedSession.workflow_runtime.checkpoint_label }}
                </template>
              </div>
            </el-descriptions-item>
          </el-descriptions>

          <div class="section-block">
            <div class="section-block__header">
              <div class="section-block__title">审计日志</div>
              <el-button text @click="reloadDetailAuditLogs">刷新</el-button>
            </div>
            <el-skeleton v-if="auditLoading" :rows="4" animated />
            <el-empty
              v-else-if="sessionAuditLogs.length === 0"
              description="暂无审计日志。"
            />
            <div v-else class="audit-list">
              <div
                v-for="item in sessionAuditLogs"
                :key="item.audit_log_id"
                class="audit-card"
              >
                <div class="audit-card__header">
                  <div class="audit-card__title">
                    <el-tag size="small" :type="auditLevelTagType(item.event_level)">
                      {{ item.event_level }}
                    </el-tag>
                    <span>{{ item.summary }}</span>
                  </div>
                  <div class="audit-card__meta">
                    {{ item.event_type }} · {{ formatDateTime(item.created_at) }}
                  </div>
                </div>
                <pre class="payload-block">{{ formatPayload(item.detail_payload) }}</pre>
              </div>
            </div>
          </div>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onMounted, reactive, ref } from "vue";

import { fetchAssistants, type AssistantSummary } from "@/api/assistants";
import type { AuditLogEntry } from "@/api/auditLogs";
import {
  createSession,
  deleteSession,
  fetchSession,
  fetchSessionAuditLogs,
  fetchSessions,
  type SessionSummary,
} from "@/api/sessions";
import { formatDateTime, formatPayload } from "@/utils/display";
import { auditLevelTagType } from "@/utils/status";

const assistants = ref<AssistantSummary[]>([]);
const sessions = ref<SessionSummary[]>([]);
const loadingAssistants = ref(false);
const loadingSessions = ref(false);
const detailLoading = ref(false);
const auditLoading = ref(false);
const submitting = ref(false);
const deletingSessionId = ref<string | null>(null);
const error = ref<string | null>(null);
const detailError = ref<string | null>(null);
const filterAssistantId = ref("");
const filterStatus = ref("");
const createDialogVisible = ref(false);
const detailDrawerVisible = ref(false);
const selectedSession = ref<SessionSummary | null>(null);
const sessionAuditLogs = ref<AuditLogEntry[]>([]);

const form = reactive({
  assistant_id: "",
  title: "",
});

const filteredSessions = computed(() =>
  sessions.value.filter((item) => !filterStatus.value || item.status === filterStatus.value),
);

function statusLabel(status: string): string {
  if (status === "active") {
    return "进行中";
  }
  if (status === "awaiting_review") {
    return "等待审核";
  }
  if (status === "awaiting_clarification") {
    return "等待澄清";
  }
  return status;
}

function statusTagType(status: string): "success" | "warning" | "info" {
  if (status === "active") {
    return "success";
  }
  if (status === "awaiting_review") {
    return "warning";
  }
  return "info";
}

function runtimeTagType(
  runtimeState?: string | null,
): "success" | "warning" | "info" | "danger" {
  if (runtimeState === "waiting_review_escalated") {
    return "danger";
  }
  if (runtimeState === "waiting_review") {
    return "warning";
  }
  if (runtimeState?.startsWith("waiting_")) {
    return "info";
  }
  if (runtimeState === "completed") {
    return "success";
  }
  return "info";
}

function runtimeQuestion(row: SessionSummary): string | null {
  const runtime = row.workflow_runtime;
  if (!runtime) {
    return null;
  }
  return runtime.pending_question || runtime.resolved_question || null;
}

async function loadAssistants() {
  loadingAssistants.value = true;
  error.value = null;

  try {
    assistants.value = await fetchAssistants();
    if (!form.assistant_id && assistants.value.length > 0) {
      form.assistant_id = assistants.value[0].assistant_id;
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "助理列表加载失败。";
  } finally {
    loadingAssistants.value = false;
  }
}

async function loadSessions() {
  loadingSessions.value = true;
  error.value = null;

  try {
    sessions.value = await fetchSessions(
      filterAssistantId.value ? { assistant_id: filterAssistantId.value } : undefined,
    );
  } catch (err) {
    error.value = err instanceof Error ? err.message : "会话列表加载失败。";
  } finally {
    loadingSessions.value = false;
  }
}

function openCreateDialog() {
  if (!form.assistant_id && assistants.value.length > 0) {
    form.assistant_id = assistants.value[0].assistant_id;
  }
  form.title = "";
  createDialogVisible.value = true;
}

async function submitSession() {
  if (!form.assistant_id) {
    ElMessage.warning("请先选择助理。");
    return;
  }

  submitting.value = true;
  try {
    await createSession({
      assistant_id: form.assistant_id,
      title: form.title.trim(),
    });
    createDialogVisible.value = false;
    form.title = "";
    ElMessage.success("会话创建成功。");
    await loadSessions();
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "会话创建失败。");
  } finally {
    submitting.value = false;
  }
}

async function loadSessionDetail(sessionId: string) {
  detailLoading.value = true;
  detailError.value = null;

  try {
    const [sessionDetail, auditLogs] = await Promise.all([
      fetchSession(sessionId),
      fetchSessionAuditLogs(sessionId, { limit: 50 }),
    ]);
    selectedSession.value = sessionDetail;
    sessionAuditLogs.value = auditLogs;
  } catch (err) {
    detailError.value = err instanceof Error ? err.message : "会话详情加载失败。";
  } finally {
    detailLoading.value = false;
  }
}

async function reloadDetailAuditLogs() {
  if (!selectedSession.value) {
    return;
  }

  auditLoading.value = true;
  try {
    sessionAuditLogs.value = await fetchSessionAuditLogs(selectedSession.value.session_id, {
      limit: 50,
    });
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "审计日志加载失败。");
  } finally {
    auditLoading.value = false;
  }
}

async function openDetailDrawer(row: SessionSummary) {
  detailDrawerVisible.value = true;
  selectedSession.value = row;
  sessionAuditLogs.value = [];
  auditLoading.value = true;
  await loadSessionDetail(row.session_id);
  auditLoading.value = false;
}

async function handleDeleteSession(row: SessionSummary) {
  try {
    await ElMessageBox.confirm(
      `删除会话“${row.title}”后，会同步清理消息、审核任务、审计日志和相关运行记录。是否继续？`,
      "删除会话",
      {
        type: "warning",
        confirmButtonText: "确认删除",
        cancelButtonText: "取消",
      },
    );
    deletingSessionId.value = row.session_id;
    const result = await deleteSession(row.session_id);
    ElMessage.success(
      `会话已删除，清理消息 ${result.deleted_message_count} 条、审核任务 ${result.deleted_review_count} 个。`,
    );
    if (selectedSession.value?.session_id === row.session_id) {
      detailDrawerVisible.value = false;
      selectedSession.value = null;
      sessionAuditLogs.value = [];
    }
    await loadSessions();
  } catch (err) {
    if (err === "cancel" || err === "close") {
      return;
    }
    ElMessage.error(err instanceof Error ? err.message : "会话删除失败。");
  } finally {
    deletingSessionId.value = null;
  }
}

onMounted(async () => {
  await loadAssistants();
  await loadSessions();
});
</script>

<style scoped>
.page-grid {
  display: grid;
  gap: 20px;
}

.page-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.page-card__title {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
}

.page-card__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.list-alert {
  margin-bottom: 16px;
}

.table-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.runtime-summary {
  display: grid;
  gap: 6px;
  color: #1f2937;
  line-height: 1.6;
}

.runtime-summary__line {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.runtime-summary__line--danger {
  color: #b91c1c;
}

.runtime-summary--idle {
  color: #6b7280;
}

.detail-layout {
  display: grid;
  gap: 20px;
}

.section-block {
  display: grid;
  gap: 12px;
}

.section-block__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.section-block__title {
  font-size: 15px;
  font-weight: 600;
}

.audit-list {
  display: grid;
  gap: 12px;
}

.audit-card {
  padding: 14px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #fff;
}

.audit-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.audit-card__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.audit-card__meta {
  color: #6b7280;
  font-size: 12px;
  white-space: nowrap;
}

.payload-block {
  margin: 0;
  padding: 12px;
  overflow-x: auto;
  border-radius: 10px;
  background: #f8fafc;
  color: #334155;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.multiline-text {
  white-space: pre-wrap;
  line-height: 1.6;
}
</style>
