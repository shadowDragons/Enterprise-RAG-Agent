<template>
  <div class="page-grid">
    <el-card shadow="never" class="action-card">
      <div class="action-card__content">
        <div class="action-card__title">知识库概览</div>
        <div class="action-card__actions">
          <el-button type="primary" @click="openCreateDialog">新建知识库</el-button>
          <el-button
            plain
            :disabled="knowledgeBases.length === 0"
            @click="openUploadDialog()"
          >
            上传文档
          </el-button>
          <el-button text @click="openJobsDrawer">任务</el-button>
        </div>
      </div>

      <div class="summary-grid">
        <div class="summary-item">
          <span class="summary-item__label">知识库数</span>
          <strong class="summary-item__value">{{ knowledgeBases.length }}</strong>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">文档总数</span>
          <strong class="summary-item__value">{{ totalDocumentCount }}</strong>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">处理中任务</span>
          <strong class="summary-item__value">{{ activeJobCount }}</strong>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">失败任务</span>
          <strong class="summary-item__value">{{ failedJobCount }}</strong>
        </div>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="page-card__header">
          <div class="page-card__title">知识库列表</div>
          <el-button text @click="refreshAll">刷新</el-button>
        </div>
      </template>

      <el-skeleton v-if="loadingKnowledgeBases" :rows="4" animated />
      <el-alert v-else-if="error" type="error" :title="error" show-icon />
      <el-empty
        v-else-if="knowledgeBases.length === 0"
        description="暂无知识库。"
      />
      <el-table v-else :data="knowledgeBases" stripe>
        <el-table-column prop="knowledge_base_name" label="名称" min-width="220" />
        <el-table-column prop="description" label="描述" min-width="260" />
        <el-table-column prop="default_retrieval_top_k" label="Top K" width="100" />
        <el-table-column label="文档数" width="110">
          <template #default="{ row }">
            <el-button text type="primary" @click="openDocumentDrawer(row)">
              {{ row.document_count }}
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="助理绑定" width="110">
          <template #default="{ row }">
            {{ row.assistant_binding_count }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="260" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button text type="primary" @click="openDocumentDrawer(row)">文档</el-button>
              <el-button text @click="openUploadDialog(row.knowledge_base_id)">上传</el-button>
              <el-button text @click="openEditDialog(row)">编辑</el-button>
              <el-button
                text
                type="danger"
                :loading="deletingKnowledgeBaseId === row.knowledge_base_id"
                @click="handleDeleteKnowledgeBase(row)"
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
      title="新建知识库"
      width="560px"
      destroy-on-close
    >
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="知识库名称">
          <el-input v-model="form.knowledge_base_name" placeholder="制度知识库" />
        </el-form-item>
        <el-form-item label="知识库描述">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="默认 Top K">
          <el-input-number v-model="form.default_retrieval_top_k" :min="1" :max="50" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-actions">
          <el-button @click="createDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="submitKnowledgeBase">
            创建
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="uploadDialogVisible"
      title="上传文档"
      width="600px"
      destroy-on-close
      @closed="handleUploadDialogClosed"
    >
      <el-alert
        v-if="knowledgeBases.length === 0 && !loadingKnowledgeBases"
        type="warning"
        title="暂无知识库，请先创建知识库。"
        show-icon
        :closable="false"
      />
      <el-form v-else label-position="top" @submit.prevent>
        <el-form-item label="目标知识库">
          <el-select
            v-model="uploadKnowledgeBaseId"
            placeholder="请选择知识库"
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
        <el-form-item label="选择文件">
          <el-upload
            ref="uploadRef"
            drag
            multiple
            accept=".txt,.md,.csv,.json,.yaml,.yml,.xml,.html,.pdf,.doc,.docx"
            :auto-upload="false"
            :limit="MAX_UPLOAD_FILE_COUNT"
            :on-change="handleFileChange"
            :on-remove="handleFileRemove"
          >
            <div class="el-upload__text">将一个或多个文件拖到此处，或点击上传</div>
            <template #tip>
              <div class="el-upload__tip">
                支持 TXT、Markdown、CSV、JSON、YAML、XML、HTML、PDF、DOC、DOCX。单次最多上传 10 个文件，上传后将创建处理任务。
              </div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-actions">
          <el-button @click="uploadDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="uploading" @click="submitDocument">
            {{ uploadButtonText }}
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="editDialogVisible"
      title="编辑知识库"
      width="560px"
      destroy-on-close
    >
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="知识库名称">
          <el-input v-model="editForm.knowledge_base_name" />
        </el-form-item>
        <el-form-item label="知识库描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="默认 Top K">
          <el-input-number
            v-model="editForm.default_retrieval_top_k"
            :min="1"
            :max="50"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-actions">
          <el-button @click="editDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="savingKnowledgeBase" @click="submitEditKnowledgeBase">
            保存
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-drawer
      v-model="documentDrawerVisible"
      :title="documentDrawerTitle"
      size="860px"
      destroy-on-close
    >
      <div class="drawer-layout">
        <div class="drawer-toolbar">
          <el-select
            v-model="documentKnowledgeBaseId"
            placeholder="按知识库查看"
            style="width: 260px"
            @change="loadDocuments"
          >
            <el-option
              v-for="item in knowledgeBases"
              :key="item.knowledge_base_id"
              :label="item.knowledge_base_name"
              :value="item.knowledge_base_id"
            />
          </el-select>
          <div class="drawer-toolbar__actions">
            <el-button
              plain
              :disabled="!documentKnowledgeBaseId"
              @click="openUploadDialog(documentKnowledgeBaseId)"
            >
              上传文档
            </el-button>
            <el-button text @click="loadDocuments">刷新</el-button>
          </div>
        </div>

        <el-alert
          v-if="selectedDocumentKnowledgeBase"
          type="info"
          :title="`${selectedDocumentKnowledgeBase.knowledge_base_name} 共 ${selectedDocumentKnowledgeBase.document_count} 份文档，默认 Top K ${selectedDocumentKnowledgeBase.default_retrieval_top_k}`"
          show-icon
          :closable="false"
        />

        <el-skeleton v-if="loadingDocuments" :rows="4" animated />
        <el-alert v-else-if="documentError" type="error" :title="documentError" show-icon />
        <el-empty
          v-else-if="documents.length === 0"
          description="暂无文档。"
        />
        <el-table v-else :data="documents" stripe>
          <el-table-column prop="file_name" label="文件名" min-width="220" />
          <el-table-column prop="mime_type" label="类型" min-width="180" />
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)">
                {{ statusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="更新时间" min-width="180">
            <template #default="{ row }">
              {{ formatDateTime(row.updated_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button
                text
                type="danger"
                :loading="deletingDocumentId === row.document_id"
                @click="handleDeleteDocument(row)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-drawer>

    <el-drawer
      v-model="jobsDrawerVisible"
      title="文档处理任务"
      size="780px"
      destroy-on-close
    >
      <div class="drawer-layout">
        <div class="drawer-toolbar drawer-toolbar--compact">
          <div class="drawer-toolbar__meta">相关处理任务可在此查看。</div>
          <el-button text @click="loadJobs">刷新</el-button>
        </div>

        <el-skeleton v-if="loadingJobs" :rows="4" animated />
        <el-alert v-else-if="jobError" type="error" :title="jobError" show-icon />
        <el-empty
          v-else-if="jobs.length === 0"
          description="暂无上传任务。"
        />
        <el-table v-else :data="jobs" stripe>
          <el-table-column label="任务类型" min-width="150">
            <template #default="{ row }">
              {{ jobTypeLabel(row.job_type) }}
            </template>
          </el-table-column>
          <el-table-column label="知识库" min-width="180">
            <template #default="{ row }">
              {{ row.knowledge_base_name || row.knowledge_base_id || "-" }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)">
                {{ statusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="进度" min-width="220">
            <template #default="{ row }">
              <el-progress :percentage="Math.round(row.progress)" />
            </template>
          </el-table-column>
          <el-table-column label="更新时间" min-width="180">
            <template #default="{ row }">
              {{ formatDateTime(row.updated_at) }}
            </template>
          </el-table-column>
          <el-table-column prop="error_message" label="错误信息" min-width="220" />
        </el-table>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from "element-plus";
import type { UploadFile, UploadInstance } from "element-plus";
import { computed, onMounted, reactive, ref } from "vue";

import {
  deleteDocument,
  fetchDocuments,
  uploadDocument,
  type DocumentSummary,
} from "@/api/documents";
import { fetchJobs, type JobSummary } from "@/api/jobs";
import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  fetchKnowledgeBases,
  updateKnowledgeBase,
  type KnowledgeBaseSummary,
} from "@/api/knowledgeBases";
import { formatDateTime } from "@/utils/display";

const MAX_UPLOAD_FILE_COUNT = 10;

const knowledgeBases = ref<KnowledgeBaseSummary[]>([]);
const documents = ref<DocumentSummary[]>([]);
const jobs = ref<JobSummary[]>([]);
const uploadRef = ref<UploadInstance>();
const loadingKnowledgeBases = ref(false);
const loadingDocuments = ref(false);
const loadingJobs = ref(false);
const submitting = ref(false);
const uploading = ref(false);
const savingKnowledgeBase = ref(false);
const deletingKnowledgeBaseId = ref<string | null>(null);
const deletingDocumentId = ref<string | null>(null);
const error = ref<string | null>(null);
const documentError = ref<string | null>(null);
const jobError = ref<string | null>(null);
const createDialogVisible = ref(false);
const editDialogVisible = ref(false);
const uploadDialogVisible = ref(false);
const documentDrawerVisible = ref(false);
const jobsDrawerVisible = ref(false);
const uploadKnowledgeBaseId = ref("");
const documentKnowledgeBaseId = ref("");
const selectedFiles = ref<File[]>([]);

const form = reactive({
  knowledge_base_name: "",
  description: "",
  default_retrieval_top_k: 5,
});

const editForm = reactive({
  knowledge_base_id: "",
  knowledge_base_name: "",
  description: "",
  default_retrieval_top_k: 5,
});

const totalDocumentCount = computed(() =>
  knowledgeBases.value.reduce((sum, item) => sum + item.document_count, 0),
);

const activeJobCount = computed(
  () =>
    jobs.value.filter((item) =>
      ["pending", "running", "processing"].includes(item.status),
    ).length,
);

const failedJobCount = computed(
  () => jobs.value.filter((item) => ["failed", "error"].includes(item.status)).length,
);

const uploadButtonText = computed(() => {
  const count = selectedFiles.value.length;
  return count > 1 ? `上传 ${count} 个文件并创建任务` : "上传并创建任务";
});

const selectedDocumentKnowledgeBase = computed(
  () =>
    knowledgeBases.value.find(
      (item) => item.knowledge_base_id === documentKnowledgeBaseId.value,
    ) ?? null,
);

const documentDrawerTitle = computed(() =>
  selectedDocumentKnowledgeBase.value
    ? `${selectedDocumentKnowledgeBase.value.knowledge_base_name} · 文档管理`
    : "文档管理",
);

function statusTagType(status: string): "success" | "warning" | "danger" | "info" {
  if (status === "ready" || status === "completed" || status === "active") {
    return "success";
  }
  if (status === "processing" || status === "pending" || status === "running") {
    return "warning";
  }
  if (status === "failed" || status === "error") {
    return "danger";
  }
  return "info";
}

function statusLabel(status: string): string {
  if (status === "ready") {
    return "就绪";
  }
  if (status === "empty") {
    return "空";
  }
  if (status === "processing") {
    return "处理中";
  }
  if (status === "pending") {
    return "待处理";
  }
  if (status === "running") {
    return "运行中";
  }
  if (status === "completed") {
    return "已完成";
  }
  if (status === "failed" || status === "error") {
    return "失败";
  }
  if (status === "active") {
    return "启用";
  }
  return status;
}

function jobTypeLabel(jobType: string): string {
  if (jobType === "document_ingestion") {
    return "文档入库";
  }
  return jobType;
}

function syncKnowledgeBaseSelections() {
  const ids = new Set(knowledgeBases.value.map((item) => item.knowledge_base_id));
  if (!ids.has(uploadKnowledgeBaseId.value)) {
    uploadKnowledgeBaseId.value = knowledgeBases.value[0]?.knowledge_base_id ?? "";
  }
  if (!ids.has(documentKnowledgeBaseId.value)) {
    documentKnowledgeBaseId.value = knowledgeBases.value[0]?.knowledge_base_id ?? "";
  }
}

function resetCreateForm() {
  form.knowledge_base_name = "";
  form.description = "";
  form.default_retrieval_top_k = 5;
}

function openCreateDialog() {
  resetCreateForm();
  createDialogVisible.value = true;
}

function openUploadDialog(knowledgeBaseId?: string) {
  syncKnowledgeBaseSelections();
  uploadKnowledgeBaseId.value =
    knowledgeBaseId ||
    uploadKnowledgeBaseId.value ||
    knowledgeBases.value[0]?.knowledge_base_id ||
    "";
  uploadDialogVisible.value = true;
}

function handleUploadDialogClosed() {
  selectedFiles.value = [];
  uploadRef.value?.clearFiles();
}

async function openDocumentDrawer(row?: KnowledgeBaseSummary) {
  syncKnowledgeBaseSelections();
  if (row) {
    documentKnowledgeBaseId.value = row.knowledge_base_id;
  }
  documentDrawerVisible.value = true;
  await loadDocuments();
}

async function openJobsDrawer() {
  jobsDrawerVisible.value = true;
  await loadJobs();
}

async function loadKnowledgeBases() {
  loadingKnowledgeBases.value = true;
  error.value = null;

  try {
    knowledgeBases.value = await fetchKnowledgeBases();
    syncKnowledgeBaseSelections();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "知识库列表加载失败。";
  } finally {
    loadingKnowledgeBases.value = false;
  }
}

async function loadDocuments() {
  documentError.value = null;
  if (!documentKnowledgeBaseId.value) {
    documents.value = [];
    return;
  }

  loadingDocuments.value = true;
  try {
    documents.value = await fetchDocuments(documentKnowledgeBaseId.value);
  } catch (err) {
    documentError.value = err instanceof Error ? err.message : "文档列表加载失败。";
  } finally {
    loadingDocuments.value = false;
  }
}

async function loadJobs() {
  loadingJobs.value = true;
  jobError.value = null;

  try {
    jobs.value = await fetchJobs({ job_type: "document_ingestion" });
  } catch (err) {
    jobError.value = err instanceof Error ? err.message : "任务列表加载失败。";
  } finally {
    loadingJobs.value = false;
  }
}

async function refreshAll() {
  await Promise.all([loadKnowledgeBases(), loadJobs()]);
  if (documentDrawerVisible.value) {
    await loadDocuments();
  }
}

async function submitKnowledgeBase() {
  if (!form.knowledge_base_name.trim()) {
    ElMessage.warning("请输入知识库名称。");
    return;
  }

  submitting.value = true;
  try {
    await createKnowledgeBase({
      knowledge_base_name: form.knowledge_base_name.trim(),
      description: form.description.trim(),
      default_retrieval_top_k: form.default_retrieval_top_k,
    });
    createDialogVisible.value = false;
    resetCreateForm();
    ElMessage.success("知识库创建成功。");
    await refreshAll();
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "知识库创建失败。");
  } finally {
    submitting.value = false;
  }
}

function openEditDialog(row: KnowledgeBaseSummary) {
  editForm.knowledge_base_id = row.knowledge_base_id;
  editForm.knowledge_base_name = row.knowledge_base_name;
  editForm.description = row.description;
  editForm.default_retrieval_top_k = row.default_retrieval_top_k;
  editDialogVisible.value = true;
}

async function submitEditKnowledgeBase() {
  if (!editForm.knowledge_base_id) {
    return;
  }
  if (!editForm.knowledge_base_name.trim()) {
    ElMessage.warning("请输入知识库名称。");
    return;
  }

  savingKnowledgeBase.value = true;
  try {
    await updateKnowledgeBase(editForm.knowledge_base_id, {
      knowledge_base_name: editForm.knowledge_base_name.trim(),
      description: editForm.description.trim(),
      default_retrieval_top_k: editForm.default_retrieval_top_k,
    });
    editDialogVisible.value = false;
    ElMessage.success("知识库更新成功。");
    await refreshAll();
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "知识库更新失败。");
  } finally {
    savingKnowledgeBase.value = false;
  }
}

async function handleDeleteKnowledgeBase(row: KnowledgeBaseSummary) {
  try {
    await ElMessageBox.confirm(
      `删除知识库“${row.knowledge_base_name}”后，会同步清理文档、向量和相关任务，并解绑关联助理。是否继续？`,
      "删除知识库",
      {
        type: "warning",
        confirmButtonText: "确认删除",
        cancelButtonText: "取消",
      },
    );
    deletingKnowledgeBaseId.value = row.knowledge_base_id;
    const result = await deleteKnowledgeBase(row.knowledge_base_id);
    if (documentKnowledgeBaseId.value === row.knowledge_base_id) {
      documents.value = [];
      documentDrawerVisible.value = false;
    }
    ElMessage.success(
      `知识库已删除，清理文档 ${result.deleted_document_count} 个，解绑助理 ${result.unbound_assistant_count} 个。`,
    );
    await refreshAll();
  } catch (err) {
    if (err === "cancel" || err === "close") {
      return;
    }
    ElMessage.error(err instanceof Error ? err.message : "知识库删除失败。");
  } finally {
    deletingKnowledgeBaseId.value = null;
  }
}

function getRawFiles(fileList: UploadFile[]): File[] {
  return fileList.flatMap((item) => (item.raw ? [item.raw as File] : []));
}

function handleFileChange(_file: UploadFile, fileList: UploadFile[]) {
  if (fileList.length > MAX_UPLOAD_FILE_COUNT) {
    uploadRef.value?.handleRemove(fileList[fileList.length - 1]);
    ElMessage.warning(`单次最多上传 ${MAX_UPLOAD_FILE_COUNT} 个文件，请分批处理。`);
    return;
  }
  selectedFiles.value = getRawFiles(fileList);
}

function handleFileRemove(_file: UploadFile, fileList: UploadFile[]) {
  selectedFiles.value = getRawFiles(fileList);
}

async function submitDocument() {
  if (!uploadKnowledgeBaseId.value) {
    ElMessage.warning("请先选择知识库。");
    return;
  }
  if (selectedFiles.value.length === 0) {
    ElMessage.warning("请先选择要上传的文件。");
    return;
  }

  uploading.value = true;
  try {
    const filesToUpload = [...selectedFiles.value];
    const failedFiles: string[] = [];
    for (const file of filesToUpload) {
      try {
        await uploadDocument(uploadKnowledgeBaseId.value, file);
      } catch {
        failedFiles.push(file.name || "未命名文件");
      }
    }
    if (failedFiles.length === filesToUpload.length) {
      throw new Error("所有文件上传失败，请稍后重试。");
    }
    documentKnowledgeBaseId.value = uploadKnowledgeBaseId.value;
    uploadDialogVisible.value = false;
    documentDrawerVisible.value = true;
    const successCount = filesToUpload.length - failedFiles.length;
    selectedFiles.value = [];
    uploadRef.value?.clearFiles();
    if (failedFiles.length > 0) {
      ElMessage.warning(
        `成功上传 ${successCount} 个文件，失败 ${failedFiles.length} 个：${failedFiles.join("、")}`,
      );
    } else {
      ElMessage.success(`成功上传 ${successCount} 个文件，任务已创建。`);
    }
    await refreshAll();
    await loadDocuments();
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "文档上传失败。");
  } finally {
    uploading.value = false;
  }
}

async function handleDeleteDocument(row: DocumentSummary) {
  try {
    await ElMessageBox.confirm(
      `删除文档“${row.file_name}”后，会同步清理索引和相关任务记录。是否继续？`,
      "删除文档",
      {
        type: "warning",
        confirmButtonText: "确认删除",
        cancelButtonText: "取消",
      },
    );
    deletingDocumentId.value = row.document_id;
    const result = await deleteDocument(row.knowledge_base_id, row.document_id);
    ElMessage.success(
      `文档已删除，清理分块 ${result.deleted_chunk_count} 个，清理任务 ${result.deleted_job_count} 个。`,
    );
    await refreshAll();
    await loadDocuments();
  } catch (err) {
    if (err === "cancel" || err === "close") {
      return;
    }
    ElMessage.error(err instanceof Error ? err.message : "文档删除失败。");
  } finally {
    deletingDocumentId.value = null;
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
  background: linear-gradient(135deg, rgba(250, 252, 255, 0.98), rgba(239, 246, 255, 0.96));
  border: 1px solid #dbeafe;
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
  color: #0f172a;
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
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(191, 219, 254, 0.85);
  display: grid;
  gap: 8px;
}

.summary-item__label {
  color: #64748b;
  font-size: 13px;
}

.summary-item__value {
  color: #0f172a;
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

.drawer-layout {
  display: grid;
  gap: 16px;
}

.drawer-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.drawer-toolbar--compact {
  align-items: flex-start;
}

.drawer-toolbar__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.drawer-toolbar__meta {
  color: #64748b;
  font-size: 13px;
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
</style>
