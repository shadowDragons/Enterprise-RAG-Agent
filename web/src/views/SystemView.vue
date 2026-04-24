<template>
  <div class="system-page">
    <el-card shadow="never">
      <template #header>
        <div class="page-card__header">
          <span>系统概览</span>
          <el-button text @click="reload">刷新</el-button>
        </div>
      </template>

      <el-skeleton v-if="systemStore.loadingOverview" :rows="8" animated />
      <el-alert
        v-else-if="systemStore.overviewError"
        type="error"
        :title="systemStore.overviewError"
        show-icon
      />
      <template v-else-if="systemStore.overview">
        <div class="hero-grid">
          <div class="hero-card">
            <div class="hero-card__label">健康状态</div>
            <div class="hero-card__value">
              <el-tag size="large" :type="healthTagType(systemStore.overview.health_status)">
                {{ healthLabel(systemStore.overview.health_status) }}
              </el-tag>
            </div>
            <div class="hero-card__meta">
              {{ systemStore.overview.summary.app_name }} · {{ systemStore.overview.summary.stage }}
            </div>
          </div>

          <div class="hero-card">
            <div class="hero-card__label">关键告警</div>
            <div class="hero-card__value">{{ criticalAlerts.length }}</div>
            <div class="hero-card__meta">按级别统计</div>
          </div>

          <div class="hero-card">
            <div class="hero-card__label">检查失败项</div>
            <div class="hero-card__value">{{ systemStore.overview.readiness.failed }}</div>
            <div class="hero-card__meta">需优先处理</div>
          </div>

          <div class="hero-card">
            <div class="hero-card__label">已升级审核</div>
            <div class="hero-card__value">{{ systemStore.overview.tasks.reviews_escalated }}</div>
            <div class="hero-card__meta">待处理</div>
          </div>

          <div class="hero-card">
            <div class="hero-card__label">失败任务数</div>
            <div class="hero-card__value">{{ systemStore.overview.tasks.jobs_failed }}</div>
            <div class="hero-card__meta">待处理</div>
          </div>
        </div>

        <div class="section-grid">
          <el-card shadow="never">
            <template #header>
              <div class="page-card__header">
                <span>上线检查</span>
                <el-tag :type="readinessTagType(systemStore.overview.readiness.overall_status)">
                  {{ readinessLabel(systemStore.overview.readiness.overall_status) }}
                </el-tag>
              </div>
            </template>
            <div class="readiness-summary">
              <div class="readiness-stat">
                <span>通过</span>
                <strong>{{ systemStore.overview.readiness.passed }}</strong>
              </div>
              <div class="readiness-stat">
                <span>预警</span>
                <strong>{{ systemStore.overview.readiness.warnings }}</strong>
              </div>
              <div class="readiness-stat">
                <span>失败</span>
                <strong>{{ systemStore.overview.readiness.failed }}</strong>
              </div>
            </div>
            <div class="readiness-list">
              <div
                v-for="check in systemStore.overview.readiness.checks"
                :key="check.code"
                class="readiness-item"
                :class="`readiness-item--${check.status}`"
              >
                <div class="readiness-item__header">
                  <el-tag :type="readinessTagType(check.status)">
                    {{ readinessLabel(check.status) }}
                  </el-tag>
                  <span class="readiness-item__title">{{ check.title }}</span>
                </div>
                <div class="readiness-item__detail">{{ check.detail }}</div>
              </div>
            </div>
          </el-card>

          <el-card shadow="never">
            <template #header>
              <div class="page-card__header">
                <span>系统维护</span>
                <el-button text :loading="systemStore.runningMaintenance" @click="reload">
                  刷新状态
                </el-button>
              </div>
            </template>
            <div v-if="canRunMaintenance" class="maintenance-actions">
              <el-button
                type="warning"
                :loading="systemStore.runningMaintenance"
                @click="handleMaintenance({ reconcile_overdue_reviews: true, retry_failed_jobs: false })"
              >
                对账审核升级
              </el-button>
              <el-button
                type="primary"
                plain
                :loading="systemStore.runningMaintenance"
                @click="handleMaintenance({ reconcile_overdue_reviews: false, retry_failed_jobs: true })"
              >
                批量重试失败任务
              </el-button>
              <el-button
                type="primary"
                :loading="systemStore.runningMaintenance"
                @click="
                  handleMaintenance({
                    reconcile_overdue_reviews: true,
                    retry_failed_jobs: true,
                  })
                "
              >
                执行完整维护
              </el-button>
            </div>
            <el-alert
              v-else
              type="info"
              title="当前账号无系统维护权限。"
              show-icon
            />
            <el-alert
              v-if="systemStore.maintenanceError"
              type="error"
              :title="systemStore.maintenanceError"
              show-icon
            />
            <div v-if="systemStore.lastMaintenanceResult" class="maintenance-result">
              <div class="maintenance-result__title">
                最近一次维护：{{ formatDateTime(systemStore.lastMaintenanceResult.executed_at) }}
              </div>
              <div class="maintenance-result__meta">
                升级审核对账 {{ systemStore.lastMaintenanceResult.reconcile_overdue_reviews_count }} 个，
                重试失败任务 {{ systemStore.lastMaintenanceResult.retried_job_count }} 个。
              </div>
              <div
                v-if="systemStore.lastMaintenanceResult.skipped_job_ids.length > 0"
                class="maintenance-result__meta"
              >
                跳过任务：{{ systemStore.lastMaintenanceResult.skipped_job_ids.join("、") }}
              </div>
            </div>
          </el-card>
        </div>

        <div class="section-grid">
          <el-card shadow="never">
            <template #header>
              <span>当前告警</span>
            </template>
            <el-empty
              v-if="systemStore.overview.alerts.length === 0"
              description="暂无系统告警。"
            />
            <div v-else class="alert-list">
              <div
                v-for="alert in systemStore.overview.alerts"
                :key="alert.code"
                class="alert-item"
                :class="`alert-item--${alert.level}`"
              >
                <div class="alert-item__header">
                  <el-tag :type="alertTagType(alert.level)">
                    {{ alert.level.toUpperCase() }}
                  </el-tag>
                  <span class="alert-item__title">{{ alert.title }}</span>
                  <span v-if="alert.count" class="alert-item__count">x{{ alert.count }}</span>
                </div>
                <div class="alert-item__detail">{{ alert.detail }}</div>
              </div>
            </div>
          </el-card>

          <el-card shadow="never">
            <template #header>
              <span>运行环境</span>
            </template>
            <el-descriptions :column="1" border>
              <el-descriptions-item label="应用环境">
                {{ systemStore.overview.runtime.app_env }}
              </el-descriptions-item>
              <el-descriptions-item label="鉴权状态">
                <el-tag :type="systemStore.overview.runtime.auth_enabled ? 'success' : 'warning'">
                  {{ systemStore.overview.runtime.auth_enabled ? "已启用" : "已关闭" }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="数据库">
                {{ systemStore.overview.runtime.database_backend }}
              </el-descriptions-item>
              <el-descriptions-item label="Qdrant">
                {{ systemStore.overview.runtime.qdrant_backend }}
              </el-descriptions-item>
              <el-descriptions-item label="工作流存储">
                {{ systemStore.overview.runtime.workflow_checkpointer_label }}
              </el-descriptions-item>
              <el-descriptions-item label="LLM 服务">
                {{ systemStore.overview.runtime.llm_provider }}
              </el-descriptions-item>
              <el-descriptions-item label="默认 LLM 模型">
                {{ systemStore.overview.runtime.llm_model }}
              </el-descriptions-item>
              <el-descriptions-item label="LLM 允许模型">
                {{ systemStore.overview.runtime.llm_allowed_models.join("、") || "-" }}
              </el-descriptions-item>
              <el-descriptions-item label="向量服务">
                {{ systemStore.overview.runtime.embedding_provider }}
              </el-descriptions-item>
              <el-descriptions-item label="默认向量模型">
                {{ systemStore.overview.runtime.embedding_model }}
              </el-descriptions-item>
              <el-descriptions-item label="向量允许模型">
                {{ systemStore.overview.runtime.embedding_allowed_models.join("、") || "-" }}
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </div>

        <div class="section-grid">
          <el-card shadow="never">
            <template #header>
              <span>资源规模</span>
            </template>
            <el-descriptions :column="1" border>
              <el-descriptions-item label="助理数">
                {{ systemStore.overview.resources.assistants_total }}
              </el-descriptions-item>
              <el-descriptions-item label="知识库数">
                {{ systemStore.overview.resources.knowledge_bases_total }}
              </el-descriptions-item>
              <el-descriptions-item label="会话总数">
                {{ systemStore.overview.resources.sessions_total }}
              </el-descriptions-item>
            </el-descriptions>
          </el-card>

          <el-card shadow="never">
            <template #header>
              <span>会话态势</span>
            </template>
            <el-descriptions :column="1" border>
              <el-descriptions-item label="活跃会话">
                {{ systemStore.overview.sessions.active }}
              </el-descriptions-item>
              <el-descriptions-item label="待澄清">
                {{ systemStore.overview.sessions.awaiting_clarification }}
              </el-descriptions-item>
              <el-descriptions-item label="待审核">
                {{ systemStore.overview.sessions.awaiting_review }}
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </div>

        <el-card shadow="never">
          <template #header>
            <span>任务风险</span>
          </template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="文档任务总数">
              {{ systemStore.overview.tasks.jobs_total }}
            </el-descriptions-item>
            <el-descriptions-item label="审核任务总数">
              {{ systemStore.overview.tasks.reviews_total }}
            </el-descriptions-item>
            <el-descriptions-item label="文档待处理 / 运行中">
              {{ systemStore.overview.tasks.jobs_pending }} / {{ systemStore.overview.tasks.jobs_running }}
            </el-descriptions-item>
            <el-descriptions-item label="审核待处理 / 已升级">
              {{ systemStore.overview.tasks.reviews_pending }} /
              {{ systemStore.overview.tasks.reviews_escalated }}
            </el-descriptions-item>
            <el-descriptions-item label="文档预警 / 超时">
              {{ systemStore.overview.tasks.jobs_warning }} / {{ systemStore.overview.tasks.jobs_breached }}
            </el-descriptions-item>
            <el-descriptions-item label="审核预警 / 超时">
              {{ systemStore.overview.tasks.reviews_warning }} /
              {{ systemStore.overview.tasks.reviews_breached }}
            </el-descriptions-item>
            <el-descriptions-item label="失败文档任务">
              {{ systemStore.overview.tasks.jobs_failed }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </template>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from "element-plus";
import { computed, onMounted } from "vue";

import { useAuthStore } from "@/stores/auth";
import { useSystemStore } from "@/stores/system";
import { formatDateTime } from "@/utils/display";

const systemStore = useSystemStore();
const authStore = useAuthStore();

const criticalAlerts = computed(() =>
  (systemStore.overview?.alerts ?? []).filter((item) => item.level === "critical"),
);
const canRunMaintenance = computed(
  () => authStore.currentUser?.permissions.includes("system:write") ?? false,
);

function healthTagType(status: string): "success" | "warning" | "danger" | "info" {
  if (status === "critical") {
    return "danger";
  }
  if (status === "warning") {
    return "warning";
  }
  return "success";
}

function healthLabel(status: string): string {
  if (status === "critical") {
    return "高风险";
  }
  if (status === "warning") {
    return "需关注";
  }
  return "正常";
}

function readinessTagType(status: string): "success" | "warning" | "danger" | "info" {
  if (status === "failed" || status === "critical") {
    return "danger";
  }
  if (status === "warning") {
    return "warning";
  }
  return "success";
}

function readinessLabel(status: string): string {
  if (status === "failed" || status === "critical") {
    return "失败";
  }
  if (status === "warning") {
    return "预警";
  }
  return "通过";
}

function alertTagType(level: string): "danger" | "warning" | "info" {
  if (level === "critical") {
    return "danger";
  }
  if (level === "warning") {
    return "warning";
  }
  return "info";
}

async function reload() {
  await systemStore.loadOverview();
}

async function handleMaintenance(payload: {
  reconcile_overdue_reviews?: boolean;
  retry_failed_jobs?: boolean;
}) {
  try {
    const result = await systemStore.runMaintenance(payload);
    ElMessage.success(
      `维护已执行：审核对账 ${result.reconcile_overdue_reviews_count} 个，重试任务 ${result.retried_job_count} 个。`,
    );
    await reload();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "系统维护执行失败。");
  }
}

onMounted(async () => {
  await reload();
});
</script>

<style scoped>
.system-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.hero-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.hero-card {
  padding: 18px;
  border: 1px solid #e5e7eb;
  border-radius: 18px;
  background:
    linear-gradient(135deg, rgba(252, 211, 77, 0.16), rgba(255, 255, 255, 0.92)),
    #fff;
}

.hero-card__label {
  color: #6b7280;
  font-size: 13px;
}

.hero-card__value {
  margin-top: 10px;
  font-size: 28px;
  font-weight: 700;
}

.hero-card__meta {
  margin-top: 8px;
  color: #6b7280;
  font-size: 12px;
}

.section-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.readiness-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.readiness-stat {
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 14px;
  background: #fff;
  display: grid;
  gap: 6px;
}

.readiness-stat span {
  color: #6b7280;
  font-size: 13px;
}

.readiness-stat strong {
  font-size: 24px;
}

.readiness-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.readiness-item {
  padding: 14px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  background: #fff;
}

.readiness-item--failed {
  border-color: #fecaca;
  background: #fff5f5;
}

.readiness-item--warning {
  border-color: #fde68a;
  background: #fffbea;
}

.readiness-item--pass {
  border-color: #bbf7d0;
  background: #f4fff6;
}

.readiness-item__header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.readiness-item__title {
  font-weight: 600;
}

.readiness-item__detail {
  margin-top: 8px;
  color: #4b5563;
  line-height: 1.6;
}

.maintenance-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.maintenance-result {
  margin-top: 14px;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  background: #fff;
  padding: 14px 16px;
}

.maintenance-result__title {
  font-weight: 600;
}

.maintenance-result__meta {
  margin-top: 8px;
  color: #4b5563;
  line-height: 1.6;
}

.alert-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.alert-item {
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid #e5e7eb;
  background: #fff;
}

.alert-item--critical {
  border-color: #fecaca;
  background: #fff4f4;
}

.alert-item--warning {
  border-color: #fde68a;
  background: #fffbea;
}

.alert-item--info {
  border-color: #bfdbfe;
  background: #f5f9ff;
}

.alert-item__header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.alert-item__title {
  font-weight: 600;
}

.alert-item__count {
  margin-left: auto;
  color: #6b7280;
  font-size: 12px;
}

.alert-item__detail {
  margin-top: 8px;
  color: #4b5563;
  line-height: 1.6;
}
</style>
