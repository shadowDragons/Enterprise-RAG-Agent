<template>
  <div class="page-grid">
    <el-card shadow="never" class="action-card">
      <div class="action-card__content">
        <div class="action-card__title">助理概览</div>
        <div class="action-card__actions">
          <el-button type="primary" @click="openCreateDialog">新建助理</el-button>
          <el-button text @click="refreshAll">刷新</el-button>
        </div>
      </div>

      <div class="summary-grid">
        <div class="summary-item">
          <span class="summary-item__label">助理总数</span>
          <strong class="summary-item__value">{{ assistants.length }}</strong>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">启用审核</span>
          <strong class="summary-item__value">{{ reviewEnabledCount }}</strong>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">关联会话数</span>
          <strong class="summary-item__value">{{ totalSessionCount }}</strong>
        </div>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="page-card__header">
          <div class="page-card__title">助理列表</div>
          <el-button text @click="refreshAll">刷新</el-button>
        </div>
      </template>

      <el-skeleton v-if="loading" :rows="4" animated />
      <el-alert v-else-if="error" type="error" :title="error" show-icon />
      <el-empty
        v-else-if="assistants.length === 0"
        description="当前还没有助理。"
      />
      <el-table v-else :data="assistants" stripe>
        <el-table-column prop="assistant_name" label="名称" min-width="220" />
        <el-table-column prop="default_model" label="模型" width="160" />
        <el-table-column label="知识库/会话" width="150">
          <template #default="{ row }">
            {{ row.default_kb_count }} / {{ row.session_count }}
          </template>
        </el-table-column>
        <el-table-column label="审核规则" width="120">
          <template #default="{ row }">
            {{ countEnabledReviewRules(row.review_rules) }} / {{ row.review_rule_count }}
          </template>
        </el-table-column>
        <el-table-column label="审核" width="100">
          <template #default="{ row }">
            <el-tag :type="row.review_enabled ? 'warning' : 'info'">
              {{ row.review_enabled ? "开启" : "关闭" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="版本" width="90">
          <template #default="{ row }">
            <el-tag type="primary">v{{ row.version }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="220" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button text type="primary" @click="openEditDialog(row)">编辑</el-button>
              <el-button text @click="openVersionDrawer(row)">版本</el-button>
              <el-button
                text
                type="danger"
                @click="handleDeleteAssistant(row)"
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
      title="新建助理"
      width="760px"
      top="4vh"
      destroy-on-close
      class="assistant-dialog"
    >
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="助理名称">
          <el-input v-model="createForm.assistant_name" placeholder="通用知识助手" />
        </el-form-item>
        <el-form-item label="助理描述">
          <el-input v-model="createForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="系统提示词">
          <el-input v-model="createForm.system_prompt" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="默认模型">
          <el-input v-model="createForm.default_model" />
        </el-form-item>
        <el-form-item label="默认知识库">
          <el-select
            v-model="createForm.default_kb_ids"
            multiple
            collapse-tags
            collapse-tags-tooltip
            clearable
            placeholder="可为空，表示运行时再选择"
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
        <div class="form-actions">
          <el-checkbox v-model="createForm.review_enabled">启用审核</el-checkbox>
        </div>
        <div class="review-rule-section">
          <div class="review-rule-toolbar">
            <div class="review-rule-toolbar__title">
              <span>审核规则</span>
              <span class="review-rule-toolbar__hint">
                支持任一关键词、全部关键词和正则三种匹配方式。
              </span>
            </div>
            <div class="review-rule-toolbar__actions">
              <el-button text @click="resetReviewRules(createForm.review_rules)">
                恢复默认规则
              </el-button>
              <el-button
                text
                type="primary"
                @click="addReviewRule(createForm.review_rules)"
              >
                新增规则
              </el-button>
            </div>
          </div>
          <div v-if="!createForm.review_enabled" class="review-rule-banner">
            审核未开启，当前规则仅保存配置，启用后才会生效。
          </div>
          <div class="review-rule-list">
            <div
              v-for="(rule, index) in createForm.review_rules"
              :key="rule.rule_id"
              class="review-rule-card"
            >
              <div class="review-rule-card__header">
                <div class="review-rule-card__title">
                  <el-tag :type="severityTagTypeMap[rule.severity]">
                    {{ severityLabelMap[rule.severity] }}风险
                  </el-tag>
                  <span>规则 {{ index + 1 }}</span>
                </div>
                <div class="review-rule-card__actions">
                  <el-switch
                    v-model="rule.enabled"
                    inline-prompt
                    active-text="启用"
                    inactive-text="停用"
                  />
                  <el-button
                    text
                    type="danger"
                    @click="removeReviewRule(createForm.review_rules, index)"
                  >
                    删除
                  </el-button>
                </div>
              </div>
              <div class="review-rule-grid">
                <el-form-item label="规则 ID">
                  <el-input v-model="rule.rule_id" />
                </el-form-item>
                <el-form-item label="规则名称">
                  <el-input v-model="rule.rule_name" />
                </el-form-item>
                <el-form-item label="分类">
                  <el-input v-model="rule.category" />
                </el-form-item>
                <el-form-item label="严重级别">
                  <el-select v-model="rule.severity" style="width: 100%">
                    <el-option
                      v-for="option in severityOptions"
                      :key="option.value"
                      :label="option.label"
                      :value="option.value"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="匹配模式">
                  <el-select v-model="rule.match_mode" style="width: 100%">
                    <el-option
                      v-for="option in matchModeOptions"
                      :key="option.value"
                      :label="option.label"
                      :value="option.value"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="优先级">
                  <el-input-number
                    v-model="rule.priority"
                    :min="1"
                    :max="9999"
                    style="width: 100%"
                  />
                </el-form-item>
                <el-form-item
                  v-if="rule.match_mode !== 'regex'"
                  label="关键词"
                  class="review-rule-grid__span-2"
                >
                  <el-select
                    v-model="rule.keywords"
                    multiple
                    filterable
                    allow-create
                    default-first-option
                    :reserve-keyword="false"
                    style="width: 100%"
                    placeholder="输入关键词后回车"
                  >
                    <el-option
                      v-for="keyword in rule.keywords"
                      :key="keyword"
                      :label="keyword"
                      :value="keyword"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item
                  v-else
                  label="正则模式"
                  class="review-rule-grid__span-2"
                >
                  <el-input
                    v-model="rule.regex_pattern"
                    placeholder="例如：(身份证号?|银行卡号?|手机号)"
                  />
                </el-form-item>
              </div>
            </div>
          </div>
        </div>
      </el-form>
      <template #footer>
        <div class="dialog-actions">
          <el-button @click="createDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="submitAssistant">
            创建
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="editDialogVisible"
      title="编辑助理"
      width="760px"
      top="4vh"
      destroy-on-close
      class="assistant-dialog"
    >
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="助理名称">
          <el-input v-model="editForm.assistant_name" />
        </el-form-item>
        <el-form-item label="助理描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="系统提示词">
          <el-input v-model="editForm.system_prompt" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="默认模型">
          <el-input v-model="editForm.default_model" />
        </el-form-item>
        <el-form-item label="默认知识库">
          <el-select
            v-model="editForm.default_kb_ids"
            multiple
            collapse-tags
            collapse-tags-tooltip
            clearable
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
        <el-form-item label="变更说明">
          <el-input
            v-model="editForm.change_note"
            type="textarea"
            :rows="2"
            placeholder="例如：切换默认知识库和模型配置"
          />
        </el-form-item>
        <div class="form-actions">
          <el-checkbox v-model="editForm.review_enabled">启用审核</el-checkbox>
        </div>
        <div class="review-rule-section">
          <div class="review-rule-toolbar">
            <div class="review-rule-toolbar__title">
              <span>审核规则</span>
              <span class="review-rule-toolbar__hint">
                审核命中会按优先级从高到低依次执行。
              </span>
            </div>
            <div class="review-rule-toolbar__actions">
              <el-button text @click="resetReviewRules(editForm.review_rules)">
                恢复默认规则
              </el-button>
              <el-button
                text
                type="primary"
                @click="addReviewRule(editForm.review_rules)"
              >
                新增规则
              </el-button>
            </div>
          </div>
          <div v-if="!editForm.review_enabled" class="review-rule-banner">
            审核未开启，规则仍会被保存，后续重新启用时直接生效。
          </div>
          <div class="review-rule-list">
            <div
              v-for="(rule, index) in editForm.review_rules"
              :key="`${editForm.assistant_id}-${rule.rule_id}`"
              class="review-rule-card"
            >
              <div class="review-rule-card__header">
                <div class="review-rule-card__title">
                  <el-tag :type="severityTagTypeMap[rule.severity]">
                    {{ severityLabelMap[rule.severity] }}风险
                  </el-tag>
                  <span>规则 {{ index + 1 }}</span>
                </div>
                <div class="review-rule-card__actions">
                  <el-switch
                    v-model="rule.enabled"
                    inline-prompt
                    active-text="启用"
                    inactive-text="停用"
                  />
                  <el-button
                    text
                    type="danger"
                    @click="removeReviewRule(editForm.review_rules, index)"
                  >
                    删除
                  </el-button>
                </div>
              </div>
              <div class="review-rule-grid">
                <el-form-item label="规则 ID">
                  <el-input v-model="rule.rule_id" />
                </el-form-item>
                <el-form-item label="规则名称">
                  <el-input v-model="rule.rule_name" />
                </el-form-item>
                <el-form-item label="分类">
                  <el-input v-model="rule.category" />
                </el-form-item>
                <el-form-item label="严重级别">
                  <el-select v-model="rule.severity" style="width: 100%">
                    <el-option
                      v-for="option in severityOptions"
                      :key="option.value"
                      :label="option.label"
                      :value="option.value"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="匹配模式">
                  <el-select v-model="rule.match_mode" style="width: 100%">
                    <el-option
                      v-for="option in matchModeOptions"
                      :key="option.value"
                      :label="option.label"
                      :value="option.value"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="优先级">
                  <el-input-number
                    v-model="rule.priority"
                    :min="1"
                    :max="9999"
                    style="width: 100%"
                  />
                </el-form-item>
                <el-form-item
                  v-if="rule.match_mode !== 'regex'"
                  label="关键词"
                  class="review-rule-grid__span-2"
                >
                  <el-select
                    v-model="rule.keywords"
                    multiple
                    filterable
                    allow-create
                    default-first-option
                    :reserve-keyword="false"
                    style="width: 100%"
                    placeholder="输入关键词后回车"
                  >
                    <el-option
                      v-for="keyword in rule.keywords"
                      :key="keyword"
                      :label="keyword"
                      :value="keyword"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item
                  v-else
                  label="正则模式"
                  class="review-rule-grid__span-2"
                >
                  <el-input
                    v-model="rule.regex_pattern"
                    placeholder="例如：(身份证号?|银行卡号?|手机号)"
                  />
                </el-form-item>
              </div>
            </div>
          </div>
        </div>
      </el-form>
      <template #footer>
        <div class="dialog-actions">
          <el-button @click="editDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="submitEditAssistant">
            保存
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-drawer
      v-model="versionDrawerVisible"
      title="助理版本记录"
      size="760px"
      destroy-on-close
    >
      <div class="version-drawer">
        <el-skeleton v-if="loadingVersions" :rows="5" animated />
        <el-alert v-else-if="versionError" type="error" :title="versionError" show-icon />
        <el-empty
          v-else-if="assistantVersions.length === 0"
          description="当前助理还没有版本记录。"
        />
        <template v-else>
          <div class="version-list">
            <div
              v-for="item in assistantVersions"
              :key="item.version"
              class="version-card"
              :class="{ 'version-card--active': selectedVersion === item.version }"
            >
              <div class="version-card__header">
                <div class="version-card__title">
                  <el-tag type="primary">v{{ item.version }}</el-tag>
                  <span>{{ item.change_note || "未填写变更说明" }}</span>
                </div>
                <div class="version-card__actions">
                  <el-button text @click="showVersionDetail(item.version)">查看</el-button>
                  <el-button
                    text
                    type="warning"
                    :loading="restoringVersion === item.version"
                    @click="handleRestoreVersion(item.version)"
                  >
                    恢复
                  </el-button>
                </div>
              </div>
              <div class="version-card__meta">
                {{ formatDateTime(item.created_at) }} · 模型 {{ item.snapshot.default_model }}
              </div>
            </div>
          </div>

          <el-divider />

          <div v-if="selectedVersionDetail" class="version-detail">
            <div class="version-detail__title">
              当前查看版本 v{{ selectedVersionDetail.version }}
            </div>
            <el-descriptions :column="1" border>
              <el-descriptions-item label="助理名称">
                {{ selectedVersionDetail.snapshot.assistant_name }}
              </el-descriptions-item>
              <el-descriptions-item label="默认模型">
                {{ selectedVersionDetail.snapshot.default_model }}
              </el-descriptions-item>
              <el-descriptions-item label="默认知识库">
                {{ selectedVersionDetail.snapshot.default_kb_ids.join("、") || "未绑定" }}
              </el-descriptions-item>
              <el-descriptions-item label="审核规则数量">
                {{ selectedVersionDetail.snapshot.review_rules.length }}
              </el-descriptions-item>
              <el-descriptions-item label="系统提示词">
                <div class="multiline-text">
                  {{ selectedVersionDetail.snapshot.system_prompt || "未填写" }}
                </div>
              </el-descriptions-item>
              <el-descriptions-item label="描述">
                <div class="multiline-text">
                  {{ selectedVersionDetail.snapshot.description || "未填写" }}
                </div>
              </el-descriptions-item>
            </el-descriptions>
            <div
              v-if="selectedVersionDetail.snapshot.review_rules.length > 0"
              class="version-rule-list"
            >
              <div
                v-for="rule in selectedVersionDetail.snapshot.review_rules"
                :key="`${selectedVersionDetail.version}-${rule.rule_id}`"
                class="version-rule-card"
              >
                <div class="version-rule-card__header">
                  <div class="version-rule-card__title">
                    <span>{{ rule.rule_name }}</span>
                    <el-tag size="small" :type="severityTagTypeMap[rule.severity]">
                      {{ severityLabelMap[rule.severity] }}风险
                    </el-tag>
                    <el-tag size="small" type="info">
                      {{ matchModeLabelMap[rule.match_mode] }}
                    </el-tag>
                  </div>
                  <el-tag size="small" :type="rule.enabled ? 'success' : 'info'">
                    {{ rule.enabled ? "启用" : "停用" }}
                  </el-tag>
                </div>
                <div class="version-rule-card__meta">
                  分类 {{ rule.category }} · 优先级 {{ rule.priority }}
                </div>
                <div class="version-rule-card__detail">
                  {{
                    rule.match_mode === "regex"
                      ? `正则：${rule.regex_pattern}`
                      : `关键词：${rule.keywords.join("、") || "未填写"}`
                  }}
                </div>
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

import {
  createAssistant,
  deleteAssistant,
  fetchAssistantVersionDetail,
  fetchAssistantVersions,
  fetchAssistants,
  restoreAssistantVersion,
  updateAssistant,
  type AssistantSummary,
  type AssistantVersionDetail,
  type AssistantVersionSummary,
  type ReviewRuleConfig,
} from "@/api/assistants";
import {
  fetchKnowledgeBases,
  type KnowledgeBaseSummary,
} from "@/api/knowledgeBases";
import { formatDateTime } from "@/utils/display";

const assistants = ref<AssistantSummary[]>([]);
const knowledgeBases = ref<KnowledgeBaseSummary[]>([]);
const assistantVersions = ref<AssistantVersionSummary[]>([]);
const selectedVersionDetail = ref<AssistantVersionDetail | null>(null);
const selectedVersion = ref<number | null>(null);
const activeAssistantId = ref("");
const loading = ref(false);
const loadingVersions = ref(false);
const submitting = ref(false);
const saving = ref(false);
const versionError = ref<string | null>(null);
const error = ref<string | null>(null);
const createDialogVisible = ref(false);
const editDialogVisible = ref(false);
const versionDrawerVisible = ref(false);
const restoringVersion = ref<number | null>(null);

const severityOptions = [
  { label: "低风险", value: "low" },
  { label: "中风险", value: "medium" },
  { label: "高风险", value: "high" },
  { label: "严重风险", value: "critical" },
] as const;

const matchModeOptions = [
  { label: "任一关键词", value: "contains_any" },
  { label: "全部关键词", value: "contains_all" },
  { label: "正则模式", value: "regex" },
] as const;

const severityLabelMap: Record<ReviewRuleConfig["severity"], string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "严重",
};

const severityTagTypeMap: Record<
  ReviewRuleConfig["severity"],
  "success" | "warning" | "danger" | "info"
> = {
  low: "success",
  medium: "warning",
  high: "danger",
  critical: "danger",
};

const matchModeLabelMap: Record<ReviewRuleConfig["match_mode"], string> = {
  contains_any: "任一关键词",
  contains_all: "全部关键词",
  regex: "正则模式",
};

const createForm = reactive({
  assistant_name: "",
  description: "",
  system_prompt: "",
  default_model: "gpt-4o",
  default_kb_ids: [] as string[],
  tool_keys: [] as string[],
  review_rules: buildDefaultReviewRules(),
  review_enabled: false,
});

const editForm = reactive({
  assistant_id: "",
  assistant_name: "",
  description: "",
  system_prompt: "",
  default_model: "gpt-4o",
  default_kb_ids: [] as string[],
  tool_keys: [] as string[],
  review_rules: [] as ReviewRuleConfig[],
  review_enabled: false,
  change_note: "",
});

const reviewEnabledCount = computed(
  () => assistants.value.filter((item) => item.review_enabled).length,
);

const totalSessionCount = computed(
  () => assistants.value.reduce((sum, item) => sum + item.session_count, 0),
);

function openCreateDialog() {
  resetCreateForm();
  createDialogVisible.value = true;
}

function resetCreateForm() {
  createForm.assistant_name = "";
  createForm.description = "";
  createForm.system_prompt = "";
  createForm.default_model = "gpt-4o";
  createForm.default_kb_ids = [];
  createForm.tool_keys = [];
  createForm.review_rules = buildDefaultReviewRules();
  createForm.review_enabled = false;
}

function buildDefaultReviewRules(): ReviewRuleConfig[] {
  return [
    {
      rule_id: "legal-risk",
      rule_name: "法律风险识别",
      category: "法律",
      severity: "critical",
      priority: 100,
      enabled: true,
      match_mode: "contains_any",
      keywords: ["起诉", "仲裁", "诉讼", "违约", "赔偿", "律师", "违法"],
      regex_pattern: "",
    },
    {
      rule_id: "privacy-risk",
      rule_name: "个人敏感信息识别",
      category: "隐私",
      severity: "critical",
      priority: 150,
      enabled: true,
      match_mode: "regex",
      keywords: [],
      regex_pattern: "(身份证号?|银行卡号?|手机号|手机号码|家庭住址|住址|隐私数据)",
    },
    {
      rule_id: "medical-risk",
      rule_name: "医疗风险识别",
      category: "医疗",
      severity: "critical",
      priority: 200,
      enabled: true,
      match_mode: "contains_any",
      keywords: ["诊断", "处方", "用药", "药量", "治疗", "症状", "怀孕"],
      regex_pattern: "",
    },
    {
      rule_id: "investment-risk",
      rule_name: "投资风险识别",
      category: "投资",
      severity: "high",
      priority: 300,
      enabled: true,
      match_mode: "contains_any",
      keywords: ["投资", "理财", "股票", "基金", "买入", "卖出", "收益率", "贷款"],
      regex_pattern: "",
    },
  ];
}

function buildEmptyReviewRule(): ReviewRuleConfig {
  return {
    rule_id: `custom-rule-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    rule_name: "自定义审核规则",
    category: "自定义",
    severity: "high",
    priority: 500,
    enabled: true,
    match_mode: "contains_any",
    keywords: [],
    regex_pattern: "",
  };
}

function cloneReviewRule(rule: ReviewRuleConfig): ReviewRuleConfig {
  return {
    rule_id: rule.rule_id,
    rule_name: rule.rule_name,
    category: rule.category,
    severity: rule.severity,
    priority: rule.priority,
    enabled: rule.enabled,
    match_mode: rule.match_mode,
    keywords: [...rule.keywords],
    regex_pattern: rule.regex_pattern,
  };
}

function addReviewRule(rules: ReviewRuleConfig[]) {
  rules.push(buildEmptyReviewRule());
}

function removeReviewRule(rules: ReviewRuleConfig[], index: number) {
  rules.splice(index, 1);
}

function resetReviewRules(rules: ReviewRuleConfig[]) {
  rules.splice(0, rules.length, ...buildDefaultReviewRules());
}

function normalizeReviewRules(rules: ReviewRuleConfig[]): ReviewRuleConfig[] {
  return rules.map((rule, index) => {
    const normalizedRuleId = rule.rule_id.trim();
    const normalizedRuleName = rule.rule_name.trim();
    const normalizedCategory = rule.category.trim();
    const normalizedPriority = Number.isFinite(rule.priority)
      ? Math.max(1, Math.trunc(rule.priority))
      : 100;
    const normalizedKeywords = Array.from(
      new Set(
        rule.keywords
          .map((item) => item.trim())
          .filter((item) => item.length > 0)
          .map((item) => item.toLowerCase()),
      ),
    ).map((item) => {
      const original = rule.keywords.find(
        (keyword) => keyword.trim().toLowerCase() === item,
      );
      return original?.trim() ?? item;
    });
    const normalizedRegexPattern = rule.regex_pattern.trim();

    if (!normalizedRuleId) {
      throw new Error(`审核规则 ${index + 1} 缺少规则 ID。`);
    }
    if (!normalizedRuleName) {
      throw new Error(`审核规则 ${index + 1} 缺少规则名称。`);
    }
    if (!normalizedCategory) {
      throw new Error(`审核规则 ${index + 1} 缺少分类。`);
    }
    if (rule.match_mode === "regex") {
      if (!normalizedRegexPattern) {
        throw new Error(`审核规则 ${index + 1} 缺少正则模式。`);
      }
      return {
        ...rule,
        rule_id: normalizedRuleId,
        rule_name: normalizedRuleName,
        category: normalizedCategory,
        priority: normalizedPriority,
        keywords: [],
        regex_pattern: normalizedRegexPattern,
      };
    }
    if (normalizedKeywords.length === 0) {
      throw new Error(`审核规则 ${index + 1} 至少需要一个关键词。`);
    }
    return {
      ...rule,
      rule_id: normalizedRuleId,
      rule_name: normalizedRuleName,
      category: normalizedCategory,
      priority: normalizedPriority,
      keywords: normalizedKeywords,
      regex_pattern: "",
    };
  });
}

function countEnabledReviewRules(rules: ReviewRuleConfig[]): number {
  return rules.filter((item) => item.enabled).length;
}

async function refreshAll() {
  loading.value = true;
  error.value = null;
  try {
    const [assistantData, knowledgeBaseData] = await Promise.all([
      fetchAssistants(),
      fetchKnowledgeBases(),
    ]);
    assistants.value = assistantData;
    knowledgeBases.value = knowledgeBaseData;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "助理列表加载失败。";
  } finally {
    loading.value = false;
  }
}

async function submitAssistant() {
  if (!createForm.assistant_name.trim()) {
    ElMessage.warning("请输入助理名称。");
    return;
  }

  submitting.value = true;
  try {
    const normalizedReviewRules = normalizeReviewRules(createForm.review_rules);
    if (createForm.review_enabled && normalizedReviewRules.length === 0) {
      throw new Error("启用审核时至少需要保留一条审核规则。");
    }
    await createAssistant({
      assistant_name: createForm.assistant_name.trim(),
      description: createForm.description.trim(),
      system_prompt: createForm.system_prompt.trim(),
      default_model: createForm.default_model.trim() || "gpt-4o",
      default_kb_ids: [...createForm.default_kb_ids],
      tool_keys: [],
      review_rules: normalizedReviewRules,
      review_enabled: createForm.review_enabled,
    });
    createDialogVisible.value = false;
    resetCreateForm();
    ElMessage.success("助理创建成功。");
    await refreshAll();
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "助理创建失败。");
  } finally {
    submitting.value = false;
  }
}

function openEditDialog(row: AssistantSummary) {
  editForm.assistant_id = row.assistant_id;
  editForm.assistant_name = row.assistant_name;
  editForm.description = row.description;
  editForm.system_prompt = row.system_prompt;
  editForm.default_model = row.default_model;
  editForm.default_kb_ids = [...row.default_kb_ids];
  editForm.tool_keys = [...row.tool_keys];
  editForm.review_rules = row.review_rules.map(cloneReviewRule);
  editForm.review_enabled = row.review_enabled;
  editForm.change_note = "";
  editDialogVisible.value = true;
}

async function submitEditAssistant() {
  if (!editForm.assistant_id) {
    return;
  }
  if (!editForm.assistant_name.trim()) {
    ElMessage.warning("请输入助理名称。");
    return;
  }

  saving.value = true;
  try {
    const normalizedReviewRules = normalizeReviewRules(editForm.review_rules);
    if (editForm.review_enabled && normalizedReviewRules.length === 0) {
      throw new Error("启用审核时至少需要保留一条审核规则。");
    }
    await updateAssistant(editForm.assistant_id, {
      assistant_name: editForm.assistant_name.trim(),
      description: editForm.description.trim(),
      system_prompt: editForm.system_prompt.trim(),
      default_model: editForm.default_model.trim() || "gpt-4o",
      default_kb_ids: [...editForm.default_kb_ids],
      tool_keys: [...editForm.tool_keys],
      review_rules: normalizedReviewRules,
      review_enabled: editForm.review_enabled,
      change_note: editForm.change_note.trim(),
    });
    editDialogVisible.value = false;
    ElMessage.success("助理更新成功。");
    await refreshAll();
    if (versionDrawerVisible.value && activeAssistantId.value === editForm.assistant_id) {
      await loadAssistantVersions(editForm.assistant_id);
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "助理更新失败。");
  } finally {
    saving.value = false;
  }
}

async function handleDeleteAssistant(row: AssistantSummary) {
  try {
    await ElMessageBox.confirm(
      `删除助理“${row.assistant_name}”后，会同步清理该助理的会话、审核任务和审计日志。是否继续？`,
      "删除助理",
      {
        type: "warning",
        confirmButtonText: "确认删除",
        cancelButtonText: "取消",
      },
    );
    const result = await deleteAssistant(row.assistant_id);
    ElMessage.success(
      `助理已删除，清理会话 ${result.deleted_session_count} 个、审核任务 ${result.deleted_review_count} 个。`,
    );
    if (activeAssistantId.value === row.assistant_id) {
      versionDrawerVisible.value = false;
    }
    await refreshAll();
  } catch (err) {
    if (err === "cancel") {
      return;
    }
    ElMessage.error(err instanceof Error ? err.message : "助理删除失败。");
  }
}

async function loadAssistantVersions(assistantId: string) {
  loadingVersions.value = true;
  versionError.value = null;
  try {
    assistantVersions.value = await fetchAssistantVersions(assistantId);
    const latestVersion = assistantVersions.value[0]?.version;
    if (latestVersion !== undefined) {
      await showVersionDetail(latestVersion);
    } else {
      selectedVersion.value = null;
      selectedVersionDetail.value = null;
    }
  } catch (err) {
    versionError.value = err instanceof Error ? err.message : "版本列表加载失败。";
  } finally {
    loadingVersions.value = false;
  }
}

async function openVersionDrawer(row: AssistantSummary) {
  activeAssistantId.value = row.assistant_id;
  versionDrawerVisible.value = true;
  await loadAssistantVersions(row.assistant_id);
}

async function showVersionDetail(version: number) {
  if (!activeAssistantId.value) {
    return;
  }
  selectedVersion.value = version;
  try {
    selectedVersionDetail.value = await fetchAssistantVersionDetail(
      activeAssistantId.value,
      version,
    );
  } catch (err) {
    versionError.value = err instanceof Error ? err.message : "版本详情加载失败。";
  }
}

async function handleRestoreVersion(version: number) {
  if (!activeAssistantId.value) {
    return;
  }
  try {
    await ElMessageBox.confirm(
      `恢复版本 v${version} 会生成一个新的当前版本，是否继续？`,
      "恢复助理版本",
      {
        type: "warning",
        confirmButtonText: "确认恢复",
        cancelButtonText: "取消",
      },
    );
    restoringVersion.value = version;
    await restoreAssistantVersion(
      activeAssistantId.value,
      version,
      `前端恢复版本 v${version}`,
    );
    ElMessage.success(`已恢复版本 v${version}。`);
    await refreshAll();
    await loadAssistantVersions(activeAssistantId.value);
  } catch (err) {
    if (err === "cancel") {
      return;
    }
    ElMessage.error(err instanceof Error ? err.message : "版本恢复失败。");
  } finally {
    restoringVersion.value = null;
  }
}

onMounted(() => {
  void refreshAll();
});
</script>

<style scoped>
.page-grid {
  display: grid;
  gap: 20px;
}

.action-card {
  background: linear-gradient(135deg, rgba(255, 251, 235, 0.96), rgba(255, 247, 237, 0.98));
  border: 1px solid #fed7aa;
}

.action-card__content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
}

.action-card__title {
  font-size: 20px;
  font-weight: 700;
  color: #7c2d12;
}

.action-card__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.summary-grid {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}

.summary-item {
  border-radius: 16px;
  padding: 16px 18px;
  background: rgba(255, 255, 255, 0.84);
  border: 1px solid rgba(253, 186, 116, 0.72);
  display: grid;
  gap: 8px;
}

.summary-item__label {
  color: #9a3412;
  font-size: 13px;
}

.summary-item__value {
  color: #7c2d12;
  font-size: 26px;
  line-height: 1;
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

.form-actions {
  display: flex;
  gap: 12px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.review-rule-section {
  display: grid;
  gap: 12px;
  margin-top: 12px;
}

.review-rule-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.review-rule-toolbar__title {
  display: grid;
  gap: 4px;
  font-weight: 600;
}

.review-rule-toolbar__hint {
  color: #6b7280;
  font-size: 13px;
  font-weight: 400;
}

.review-rule-toolbar__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.review-rule-banner {
  border-radius: 12px;
  background: #f8fafc;
  color: #475569;
  padding: 10px 12px;
  font-size: 13px;
}

.review-rule-list {
  display: grid;
  gap: 12px;
}

.review-rule-card {
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  background: #ffffff;
  padding: 16px;
  display: grid;
  gap: 14px;
}

.review-rule-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.review-rule-card__title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
}

.review-rule-card__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.review-rule-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.review-rule-grid__span-2 {
  grid-column: 1 / -1;
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

.version-drawer {
  display: grid;
  gap: 20px;
}

.version-list {
  display: grid;
  gap: 12px;
}

.version-card {
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 14px 16px;
  background: #fff;
}

.version-card--active {
  border-color: #409eff;
  box-shadow: 0 0 0 1px rgba(64, 158, 255, 0.18);
}

.version-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.version-card__title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
}

.version-card__actions {
  display: flex;
  gap: 8px;
}

.version-card__meta {
  margin-top: 8px;
  color: #6b7280;
  font-size: 13px;
}

.version-detail {
  display: grid;
  gap: 12px;
}

.version-detail__title {
  font-size: 15px;
  font-weight: 600;
}

.version-rule-list {
  display: grid;
  gap: 10px;
}

.version-rule-card {
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 12px 14px;
  background: #fff;
  display: grid;
  gap: 8px;
}

.version-rule-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.version-rule-card__title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-weight: 600;
}

.version-rule-card__meta,
.version-rule-card__detail {
  color: #6b7280;
  font-size: 13px;
}

.multiline-text {
  white-space: pre-wrap;
  line-height: 1.6;
}

:deep(.assistant-dialog .el-dialog__body) {
  max-height: calc(100vh - 220px);
  overflow-y: auto;
}

@media (max-width: 768px) {
  .review-rule-grid {
    grid-template-columns: 1fr;
  }
}
</style>
