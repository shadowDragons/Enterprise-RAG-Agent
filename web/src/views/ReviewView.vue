<template>
  <div class="page-grid">
    <el-card shadow="never">
      <template #header>
        <div class="page-card__header">
          <span>审核台</span>
          <div class="toolbar">
            <el-select
              v-model="selectedStatus"
              placeholder="筛选状态"
              style="width: 180px"
              @change="loadReviewTasks"
            >
              <el-option label="全部" value="" />
              <el-option label="待审核" value="pending" />
              <el-option label="已升级" value="escalated" />
              <el-option label="已通过" value="approved" />
              <el-option label="已驳回" value="rejected" />
            </el-select>
            <el-button text @click="loadReviewTasks">刷新</el-button>
          </div>
        </div>
      </template>

      <el-skeleton v-if="loading" :rows="5" animated />
      <el-alert v-else-if="error" type="error" :title="error" show-icon />
      <el-empty
        v-else-if="reviewTasks.length === 0"
        description="暂无审核任务。"
      />
      <el-table v-else :data="reviewTasks" stripe>
        <el-table-column prop="assistant_name" label="助理" width="160" />
        <el-table-column prop="session_title" label="会话" min-width="180" />
        <el-table-column prop="question" label="问题" min-width="260" />
        <el-table-column prop="review_reason" label="命中原因" min-width="220" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)">
              {{ statusLabel(row.status) }}
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
        <el-table-column label="命中数" width="100">
          <template #default="{ row }">
            {{ row.retrieval_count }}
          </template>
        </el-table-column>
        <el-table-column label="SLA 时钟" min-width="220">
          <template #default="{ row }">
            {{ slaClockText(row.sla) }}
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button text @click="openReviewTask(row.review_id)">详情</el-button>
            <el-button
              v-if="row.status === 'pending' || row.status === 'escalated'"
              text
              type="primary"
              @click="openReviewTask(row.review_id)"
            >
              审核
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer
      v-model="detailVisible"
      title="审核详情"
      size="48%"
      destroy-on-close
    >
      <el-skeleton v-if="detailLoading" :rows="8" animated />
      <el-alert
        v-else-if="detailError"
        type="error"
        :title="detailError"
        show-icon
      />
      <template v-else-if="selectedReviewTask">
        <div class="detail-layout">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="助理">
              {{ selectedReviewTask.assistant_name }}
            </el-descriptions-item>
            <el-descriptions-item label="会话">
              {{ selectedReviewTask.session_title }}
            </el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="statusTagType(selectedReviewTask.status)">
                {{ statusLabel(selectedReviewTask.status) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="SLA 状态">
              <el-tag :type="slaTagType(selectedReviewTask.sla.status)">
                {{ slaStatusLabel(selectedReviewTask.sla.status) }}
              </el-tag>
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
            <el-descriptions-item
              v-if="selectedReviewTask.reviewer_note"
              label="审核意见"
            >
              {{ selectedReviewTask.reviewer_note }}
            </el-descriptions-item>
            <el-descriptions-item
              v-if="selectedReviewTask.final_answer"
              label="最终结论"
            >
              {{ selectedReviewTask.final_answer }}
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
            <div class="section-block__title">执行轨迹</div>
            <div class="trace-list">
              <div
                v-for="(step, index) in selectedReviewTask.workflow_trace"
                :key="`${step.node}-${index}`"
                class="trace-step"
              >
                <div class="trace-step__node">{{ step.node }}</div>
                <div class="trace-step__detail">{{ step.detail }}</div>
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
                  placeholder="例如：确认可继续自动生成，或必须转人工处理。"
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
                <el-button
                  type="primary"
                  :loading="approving"
                  @click="handleApprove"
                >
                  审核通过并继续生成
                </el-button>
                <el-button
                  type="danger"
                  plain
                  :loading="rejecting"
                  @click="handleReject"
                >
                  驳回并写入人工结论
                </el-button>
              </div>
            </el-form>
          </div>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from "element-plus";
import { onMounted, ref } from "vue";

import {
  approveReviewTask,
  fetchReviewTask,
  fetchReviewTasks,
  rejectReviewTask,
  type ReviewTaskDetail,
  type ReviewTaskSummary,
} from "@/api/reviews";
import { formatDateTime } from "@/utils/display";
import {
  reviewStatusLabel as statusLabel,
  reviewStatusTagType as statusTagType,
} from "@/utils/status";
import { slaClockText, slaStatusLabel, slaTagType } from "@/utils/taskSla";

const selectedStatus = ref("");
const reviewTasks = ref<ReviewTaskSummary[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const detailVisible = ref(false);
const selectedReviewTask = ref<ReviewTaskDetail | null>(null);
const detailLoading = ref(false);
const detailError = ref<string | null>(null);
const reviewerNote = ref("");
const manualAnswer = ref("");
const approving = ref(false);
const rejecting = ref(false);

async function loadReviewTasks() {
  loading.value = true;
  error.value = null;
  try {
    reviewTasks.value = await fetchReviewTasks({
      status: selectedStatus.value || undefined,
    });
  } catch (err) {
    error.value = err instanceof Error ? err.message : "审核任务加载失败。";
  } finally {
    loading.value = false;
  }
}

async function openReviewTask(reviewId: string) {
  detailVisible.value = true;
  detailLoading.value = true;
  detailError.value = null;
  reviewerNote.value = "";
  manualAnswer.value = "";
  try {
    selectedReviewTask.value = await fetchReviewTask(reviewId);
  } catch (err) {
    detailError.value = err instanceof Error ? err.message : "审核详情加载失败。";
  } finally {
    detailLoading.value = false;
  }
}

async function reloadDetail() {
  if (!selectedReviewTask.value) {
    return;
  }
  selectedReviewTask.value = await fetchReviewTask(selectedReviewTask.value.review_id);
}

async function handleApprove() {
  if (!selectedReviewTask.value) {
    return;
  }
  approving.value = true;
  try {
    selectedReviewTask.value = await approveReviewTask(
      selectedReviewTask.value.review_id,
      reviewerNote.value.trim(),
    );
    await loadReviewTasks();
    ElMessage.success("审核已通过，并已恢复生成。");
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "审核通过失败。");
    await reloadDetail();
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
    selectedReviewTask.value = await rejectReviewTask(
      selectedReviewTask.value.review_id,
      {
        reviewerNote: reviewerNote.value.trim(),
        manualAnswer: manualAnswer.value.trim(),
      },
    );
    await loadReviewTasks();
    ElMessage.success("已驳回自动回答，并写入人工结论。");
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "驳回失败。");
    await reloadDetail();
  } finally {
    rejecting.value = false;
  }
}

onMounted(() => {
  void loadReviewTasks();
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
  gap: 12px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
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
.trace-list {
  display: grid;
  gap: 12px;
}

.citation-card,
.trace-step {
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 14px;
  background: #f8fafc;
}

.citation-card__meta,
.trace-step__node {
  color: #475569;
  font-size: 13px;
  margin-bottom: 8px;
}

.citation-card__content,
.trace-step__detail {
  color: #111827;
  line-height: 1.7;
  white-space: pre-wrap;
}

.action-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
</style>
