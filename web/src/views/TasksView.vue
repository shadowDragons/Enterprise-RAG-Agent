<template>
  <div class="page-grid">
    <div class="stats-grid">
      <el-card shadow="never" class="stat-card">
        <div class="stat-card__label">文档任务总数</div>
        <div class="stat-card__value">{{ jobs.length }}</div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-card__label">处理中任务</div>
        <div class="stat-card__value">{{ activeJobCount }}</div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-card__label">待审核任务</div>
        <div class="stat-card__value">{{ pendingReviewCount }}</div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-card__label">SLA 预警</div>
        <div class="stat-card__value">{{ warningTaskCount }}</div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-card__label">SLA 超时</div>
        <div class="stat-card__value">{{ breachedTaskCount }}</div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-card__label">失败任务</div>
        <div class="stat-card__value">{{ failedJobCount }}</div>
      </el-card>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="page-card__header">
          <span>文档处理任务</span>
          <div class="page-card__actions">
            <el-button
              v-if="retryableSelectedJobs.length > 0"
              type="warning"
              plain
              :loading="batchRetrying"
              @click="handleBatchRetryJobs"
            >
              批量重试 {{ retryableSelectedJobs.length }} 个
            </el-button>
            <el-select
              v-model="jobStatus"
              clearable
              placeholder="筛选状态"
              style="width: 180px"
              @change="loadJobs"
            >
              <el-option label="待处理" value="pending" />
              <el-option label="运行中" value="running" />
              <el-option label="已完成" value="completed" />
              <el-option label="失败" value="failed" />
            </el-select>
            <el-select
              v-model="jobSlaStatus"
              clearable
              placeholder="筛选SLA"
              style="width: 180px"
              @change="loadJobs"
            >
              <el-option label="正常" value="normal" />
              <el-option label="预警" value="warning" />
              <el-option label="超时" value="breached" />
              <el-option label="已完成" value="completed" />
              <el-option label="失败" value="failed" />
            </el-select>
            <el-button text @click="loadJobs">刷新</el-button>
          </div>
        </div>
      </template>

      <el-skeleton v-if="loadingJobs" :rows="4" animated />
      <el-alert v-else-if="jobError" type="error" :title="jobError" show-icon />
      <el-empty
        v-else-if="jobs.length === 0"
        description="暂无文档处理任务。"
      />
      <el-table
        v-else
        :data="jobs"
        stripe
        @selection-change="handleJobSelectionChange"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column label="文档" min-width="220">
          <template #default="{ row }">
            {{ row.target_name || row.target_id }}
          </template>
        </el-table-column>
        <el-table-column label="知识库" min-width="180">
          <template #default="{ row }">
            {{ row.knowledge_base_name || row.knowledge_base_id || "-" }}
          </template>
        </el-table-column>
        <el-table-column label="任务状态" width="120">
          <template #default="{ row }">
            <el-tag :type="jobStatusTagType(row.status)">
              {{ jobStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="目标状态" width="120">
          <template #default="{ row }">
            <el-tag :type="targetStatusTagType(row.target_status)">
              {{ targetStatusLabel(row.target_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="SLA" width="120">
          <template #default="{ row }">
            <el-tag :type="slaTagType(row.sla.status)">
              {{ slaStatusLabel(row.sla.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" min-width="220">
          <template #default="{ row }">
            <el-progress :percentage="Math.round(row.progress)" />
          </template>
        </el-table-column>
        <el-table-column label="SLA 时钟" min-width="220">
          <template #default="{ row }">
            {{ slaClockText(row.sla) }}
          </template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button text type="primary" @click="selectedJob = row">详情</el-button>
              <el-button
                v-if="row.retryable"
                text
                type="warning"
                :loading="retryingJobId === row.job_id"
                @click="handleRetryJob(row)"
              >
                重试
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="page-card__header">
          <span>审核任务</span>
          <div class="page-card__actions">
            <el-select
              v-model="reviewStatus"
              clearable
              placeholder="筛选状态"
              style="width: 180px"
              @change="loadReviewTasks"
            >
              <el-option label="待审核" value="pending" />
              <el-option label="已升级" value="escalated" />
              <el-option label="已通过" value="approved" />
              <el-option label="已驳回" value="rejected" />
            </el-select>
            <el-select
              v-model="reviewSlaStatus"
              clearable
              placeholder="筛选SLA"
              style="width: 180px"
              @change="loadReviewTasks"
            >
              <el-option label="正常" value="normal" />
              <el-option label="预警" value="warning" />
              <el-option label="超时" value="breached" />
              <el-option label="已完成" value="completed" />
            </el-select>
            <el-button text @click="loadReviewTasks">刷新</el-button>
          </div>
        </div>
      </template>

      <el-skeleton v-if="loadingReviews" :rows="4" animated />
      <el-alert v-else-if="reviewError" type="error" :title="reviewError" show-icon />
      <el-empty
        v-else-if="reviewTasks.length === 0"
        description="暂无审核任务。"
      />
      <el-table v-else :data="reviewTasks" stripe>
        <el-table-column prop="assistant_name" label="助理" width="160" />
        <el-table-column prop="session_title" label="会话" min-width="180" />
        <el-table-column prop="question" label="问题" min-width="280" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="reviewStatusTagType(row.status)">
              {{ reviewStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="SLA" width="120">
          <template #default="{ row }">
            <el-tag :type="slaTagType(row.sla.status)">
              {{ slaStatusLabel(row.sla.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="review_reason" label="命中原因" min-width="220" />
        <el-table-column label="SLA 时钟" min-width="220">
          <template #default="{ row }">
            {{ slaClockText(row.sla) }}
          </template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" @click="openReviewDrawer(row.review_id)">
              详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="jobDetailVisible"
      title="任务详情"
      width="680px"
      destroy-on-close
    >
      <template v-if="selectedJob">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="任务类型">
            {{ jobTypeLabel(selectedJob.job_type) }}
          </el-descriptions-item>
          <el-descriptions-item label="文档">
            {{ selectedJob.target_name || selectedJob.target_id }}
          </el-descriptions-item>
          <el-descriptions-item label="知识库">
            {{ selectedJob.knowledge_base_name || selectedJob.knowledge_base_id || "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="任务状态">
            {{ jobStatusLabel(selectedJob.status) }}
          </el-descriptions-item>
          <el-descriptions-item label="目标状态">
            {{ targetStatusLabel(selectedJob.target_status) }}
          </el-descriptions-item>
          <el-descriptions-item label="SLA 状态">
            <el-tag :type="slaTagType(selectedJob.sla.status)">
              {{ slaStatusLabel(selectedJob.sla.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="SLA 策略">
            {{ selectedJob.sla.policy_name }} · {{ formatDuration(selectedJob.sla.target_seconds) }}
          </el-descriptions-item>
          <el-descriptions-item label="SLA 截止">
            {{ formatDateTime(selectedJob.sla.deadline_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="进度">
            <el-progress :percentage="Math.round(selectedJob.progress)" />
          </el-descriptions-item>
          <el-descriptions-item label="SLA 时钟">
            {{ slaClockText(selectedJob.sla) }}
          </el-descriptions-item>
          <el-descriptions-item label="错误信息">
            {{ selectedJob.error_message || "无" }}
          </el-descriptions-item>
          <el-descriptions-item label="更新时间">
            {{ formatDateTime(selectedJob.updated_at) }}
          </el-descriptions-item>
        </el-descriptions>
        <div v-if="selectedJob.retryable" class="dialog-actions">
          <el-button
            type="warning"
            :loading="retryingJobId === selectedJob.job_id"
            @click="handleRetryJob(selectedJob)"
          >
            重试任务
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-drawer
      v-model="reviewDrawerVisible"
      title="审核任务详情"
      size="820px"
      destroy-on-close
    >
      <div class="detail-layout">
        <el-skeleton v-if="reviewDetailLoading" :rows="8" animated />
        <el-alert
          v-else-if="reviewDetailError"
          type="error"
          :title="reviewDetailError"
          show-icon
        />
        <template v-else-if="selectedReviewTask">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="助理">
              {{ selectedReviewTask.assistant_name }}
            </el-descriptions-item>
            <el-descriptions-item label="会话">
              {{ selectedReviewTask.session_title }}
            </el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="reviewStatusTagType(selectedReviewTask.status)">
                {{ reviewStatusLabel(selectedReviewTask.status) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="SLA 状态">
              <el-tag :type="slaTagType(selectedReviewTask.sla.status)">
                {{ slaStatusLabel(selectedReviewTask.sla.status) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="SLA 策略">
              {{
                selectedReviewTask.sla.policy_name
              }} · {{ formatDuration(selectedReviewTask.sla.target_seconds) }}
            </el-descriptions-item>
            <el-descriptions-item label="SLA 截止">
              {{ formatDateTime(selectedReviewTask.sla.deadline_at) }}
            </el-descriptions-item>
            <el-descriptions-item label="SLA 时钟">
              {{ slaClockText(selectedReviewTask.sla) }}
            </el-descriptions-item>
            <el-descriptions-item
              v-if="selectedReviewTask.escalation_reason"
              label="升级原因"
            >
              {{ selectedReviewTask.escalation_reason }}
            </el-descriptions-item>
            <el-descriptions-item
              v-if="selectedReviewTask.escalated_at"
              label="升级时间"
            >
              {{ formatDateTime(selectedReviewTask.escalated_at) }}
            </el-descriptions-item>
            <el-descriptions-item label="问题">
              {{ selectedReviewTask.question }}
            </el-descriptions-item>
            <el-descriptions-item label="命中原因">
              {{ selectedReviewTask.review_reason }}
            </el-descriptions-item>
            <el-descriptions-item label="知识库范围">
              {{
                selectedReviewTask.selected_kb_ids.length > 0
                  ? selectedReviewTask.selected_kb_ids.join("、")
                  : selectedReviewTask.selected_knowledge_base_id || "未指定"
              }}
            </el-descriptions-item>
            <el-descriptions-item label="最终结论">
              {{ selectedReviewTask.final_answer || "暂无" }}
            </el-descriptions-item>
          </el-descriptions>

          <div class="section-block">
            <div class="section-block__title">引用片段</div>
            <el-empty
              v-if="selectedReviewTask.citations.length === 0"
              description="暂无引用片段。"
            />
            <div v-else class="citation-list">
              <div
                v-for="citation in selectedReviewTask.citations"
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

          <div class="section-block">
            <div class="section-block__title">审核审计</div>
            <el-skeleton v-if="reviewAuditLoading" :rows="4" animated />
            <el-empty
              v-else-if="reviewAuditLogs.length === 0"
              description="暂无审核日志。"
            />
            <div v-else class="audit-list">
              <div
                v-for="item in reviewAuditLogs"
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

          <div
            v-if="
              selectedReviewTask.status === 'pending' ||
              selectedReviewTask.status === 'escalated'
            "
            class="section-block"
          >
            <div class="section-block__title">审核操作</div>
            <el-form label-position="top" @submit.prevent>
              <el-form-item label="审核意见">
                <el-input
                  v-model="reviewerNote"
                  type="textarea"
                  :rows="3"
                  placeholder="例如：允许继续自动生成，或要求转人工处理。"
                />
              </el-form-item>
              <el-form-item label="人工结论（仅驳回时可填）">
                <el-input
                  v-model="manualAnswer"
                  type="textarea"
                  :rows="4"
                  placeholder="如需驳回自动回答，可填写人工处理结论。"
                />
              </el-form-item>
              <div class="action-row">
                <el-button type="primary" :loading="approving" @click="handleApprove">
                  审核通过
                </el-button>
                <el-button type="danger" plain :loading="rejecting" @click="handleReject">
                  驳回并写入结论
                </el-button>
              </div>
            </el-form>
          </div>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from "element-plus";
import { computed, onMounted, ref, watch } from "vue";

import type { AuditLogEntry } from "@/api/auditLogs";
import {
  fetchJobs,
  retryJob,
  retryJobsBatch,
  type JobSummary,
} from "@/api/jobs";
import {
  approveReviewTask,
  fetchReviewAuditLogs,
  fetchReviewTask,
  fetchReviewTasks,
  rejectReviewTask,
  type ReviewTaskDetail,
  type ReviewTaskSummary,
} from "@/api/reviews";
import { formatDateTime, formatPayload } from "@/utils/display";
import {
  auditLevelTagType,
  reviewStatusLabel,
  reviewStatusTagType,
} from "@/utils/status";
import {
  formatDuration,
  slaClockText,
  slaStatusLabel,
  slaTagType,
} from "@/utils/taskSla";

const jobs = ref<JobSummary[]>([]);
const reviewTasks = ref<ReviewTaskSummary[]>([]);
const loadingJobs = ref(false);
const loadingReviews = ref(false);
const reviewDetailLoading = ref(false);
const reviewAuditLoading = ref(false);
const approving = ref(false);
const rejecting = ref(false);
const retryingJobId = ref<string | null>(null);
const batchRetrying = ref(false);
const jobError = ref<string | null>(null);
const reviewError = ref<string | null>(null);
const reviewDetailError = ref<string | null>(null);
const jobStatus = ref("");
const reviewStatus = ref("");
const jobSlaStatus = ref("");
const reviewSlaStatus = ref("");
const selectedJob = ref<JobSummary | null>(null);
const selectedReviewTask = ref<ReviewTaskDetail | null>(null);
const reviewAuditLogs = ref<AuditLogEntry[]>([]);
const reviewDrawerVisible = ref(false);
const reviewerNote = ref("");
const manualAnswer = ref("");
const selectedJobRows = ref<JobSummary[]>([]);

const jobDetailVisible = computed({
  get: () => selectedJob.value !== null,
  set: (value: boolean) => {
    if (!value) {
      selectedJob.value = null;
    }
  },
});

const activeJobCount = computed(
  () => jobs.value.filter((item) => item.status === "pending" || item.status === "running").length,
);
const failedJobCount = computed(
  () => jobs.value.filter((item) => item.status === "failed").length,
);
const retryableSelectedJobs = computed(() =>
  selectedJobRows.value.filter((item) => item.retryable),
);
const pendingReviewCount = computed(
  () =>
    reviewTasks.value.filter(
      (item) => item.status === "pending" || item.status === "escalated",
    ).length,
);
const warningTaskCount = computed(
  () =>
    jobs.value.filter((item) => item.sla.status === "warning").length +
    reviewTasks.value.filter((item) => item.sla.status === "warning").length,
);
const breachedTaskCount = computed(
  () =>
    jobs.value.filter((item) => item.sla.status === "breached").length +
    reviewTasks.value.filter((item) => item.sla.status === "breached").length,
);

watch(reviewDrawerVisible, (visible) => {
  if (!visible) {
    selectedReviewTask.value = null;
    reviewAuditLogs.value = [];
    reviewerNote.value = "";
    manualAnswer.value = "";
    reviewDetailError.value = null;
  }
});

function jobStatusTagType(status: string): "success" | "warning" | "danger" | "info" {
  if (status === "completed") {
    return "success";
  }
  if (status === "pending" || status === "running") {
    return "warning";
  }
  if (status === "failed") {
    return "danger";
  }
  return "info";
}

function jobStatusLabel(status: string): string {
  if (status === "pending") {
    return "待处理";
  }
  if (status === "running") {
    return "运行中";
  }
  if (status === "completed") {
    return "已完成";
  }
  if (status === "failed") {
    return "失败";
  }
  return status;
}

function targetStatusTagType(status?: string | null): "success" | "warning" | "danger" | "info" {
  if (status === "ready") {
    return "success";
  }
  if (status === "processing") {
    return "warning";
  }
  if (status === "failed") {
    return "danger";
  }
  return "info";
}

function targetStatusLabel(status?: string | null): string {
  if (!status) {
    return "-";
  }
  if (status === "ready") {
    return "就绪";
  }
  if (status === "processing") {
    return "处理中";
  }
  if (status === "failed") {
    return "失败";
  }
  return status;
}

function jobTypeLabel(jobType: string): string {
  if (jobType === "document_ingestion") {
    return "文档入库";
  }
  return jobType;
}

async function loadJobs() {
  loadingJobs.value = true;
  jobError.value = null;

  try {
    jobs.value = await fetchJobs({
      job_type: "document_ingestion",
      status: jobStatus.value || undefined,
      sla_status: jobSlaStatus.value || undefined,
    });
    selectedJobRows.value = [];
  } catch (err) {
    jobError.value = err instanceof Error ? err.message : "任务列表加载失败。";
  } finally {
    loadingJobs.value = false;
  }
}

async function handleRetryJob(job: JobSummary) {
  retryingJobId.value = job.job_id;
  try {
    const retriedJob = await retryJob(job.job_id);
    ElMessage.success("任务已重新提交。");
    await loadJobs();
    if (selectedJob.value?.job_id === job.job_id) {
      selectedJob.value = jobs.value.find((item) => item.job_id === job.job_id) ?? retriedJob;
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "任务重试失败。");
  } finally {
    retryingJobId.value = null;
  }
}

function handleJobSelectionChange(rows: JobSummary[]) {
  selectedJobRows.value = rows;
}

async function handleBatchRetryJobs() {
  if (retryableSelectedJobs.value.length === 0) {
    ElMessage.warning("请先选择可重试的失败任务。");
    return;
  }

  batchRetrying.value = true;
  try {
    const result = await retryJobsBatch({
      job_ids: retryableSelectedJobs.value.map((item) => item.job_id),
      limit: retryableSelectedJobs.value.length,
    });
    ElMessage.success(
      `已批量提交 ${result.retried_count} 个任务重试。`,
    );
    selectedJobRows.value = [];
    await loadJobs();
    if (selectedJob.value) {
      selectedJob.value =
        jobs.value.find((item) => item.job_id === selectedJob.value?.job_id) ?? null;
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "批量重试失败。");
  } finally {
    batchRetrying.value = false;
  }
}

async function loadReviewTasks() {
  loadingReviews.value = true;
  reviewError.value = null;

  try {
    reviewTasks.value = await fetchReviewTasks({
      status: reviewStatus.value || undefined,
      sla_status: reviewSlaStatus.value || undefined,
    });
  } catch (err) {
    reviewError.value = err instanceof Error ? err.message : "审核任务加载失败。";
  } finally {
    loadingReviews.value = false;
  }
}

async function openReviewDrawer(reviewId: string) {
  reviewDrawerVisible.value = true;
  reviewDetailLoading.value = true;
  reviewAuditLoading.value = true;
  reviewDetailError.value = null;

  try {
    const [detail, auditLogs] = await Promise.all([
      fetchReviewTask(reviewId),
      fetchReviewAuditLogs(reviewId, { limit: 50 }),
    ]);
    selectedReviewTask.value = detail;
    reviewAuditLogs.value = auditLogs;
    reviewerNote.value = detail.reviewer_note || "";
    manualAnswer.value = detail.final_answer || "";
  } catch (err) {
    reviewDetailError.value = err instanceof Error ? err.message : "审核详情加载失败。";
  } finally {
    reviewDetailLoading.value = false;
    reviewAuditLoading.value = false;
  }
}

async function handleApprove() {
  if (!selectedReviewTask.value) {
    return;
  }

  approving.value = true;
  try {
    selectedReviewTask.value = await approveReviewTask(
      selectedReviewTask.value.review_id,
      reviewerNote.value,
    );
    reviewAuditLogs.value = await fetchReviewAuditLogs(selectedReviewTask.value.review_id, {
      limit: 50,
    });
    ElMessage.success("审核已通过。");
    await loadReviewTasks();
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "审核通过失败。");
  } finally {
    approving.value = false;
  }
}

async function handleReject() {
  if (!selectedReviewTask.value) {
    return;
  }

  rejecting.value = true;
  try {
    selectedReviewTask.value = await rejectReviewTask(selectedReviewTask.value.review_id, {
      reviewerNote: reviewerNote.value,
      manualAnswer: manualAnswer.value,
    });
    reviewAuditLogs.value = await fetchReviewAuditLogs(selectedReviewTask.value.review_id, {
      limit: 50,
    });
    ElMessage.success("审核已驳回。");
    await loadReviewTasks();
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "审核驳回失败。");
  } finally {
    rejecting.value = false;
  }
}

onMounted(() => {
  void Promise.all([loadJobs(), loadReviewTasks()]);
});
</script>

<style scoped>
.page-grid {
  display: grid;
  gap: 20px;
}

.stats-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}

.stat-card__label {
  color: #6b7280;
  font-size: 13px;
}

.stat-card__value {
  margin-top: 10px;
  font-size: 30px;
  font-weight: 700;
  color: #111827;
}

.page-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.page-card__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.table-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.detail-layout {
  display: grid;
  gap: 20px;
}

.section-block {
  display: grid;
  gap: 12px;
}

.section-block__title {
  font-size: 15px;
  font-weight: 600;
}

.citation-list,
.audit-list {
  display: grid;
  gap: 12px;
}

.citation-card,
.audit-card {
  padding: 14px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #fff;
}

.citation-card__meta,
.audit-card__meta {
  color: #6b7280;
  font-size: 12px;
}

.citation-card__content {
  margin-top: 8px;
  white-space: pre-wrap;
  line-height: 1.6;
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

.payload-block {
  margin: 12px 0 0;
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

.action-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
