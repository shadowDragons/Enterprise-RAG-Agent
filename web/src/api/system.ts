import { apiClient } from "./client";

export interface SystemSummary {
  app_name: string;
  version: string;
  stage: string;
  frontend_stack: string;
  backend_stack: string;
}

export interface SystemRuntimeOverview {
  app_env: string;
  auth_enabled: boolean;
  database_backend: string;
  qdrant_backend: string;
  workflow_checkpointer_backend: string;
  workflow_checkpointer_label: string;
  llm_provider: string;
  llm_model: string;
  llm_allowed_models: string[];
  embedding_provider: string;
  embedding_model: string;
  embedding_allowed_models: string[];
}

export interface SystemResourceCounts {
  assistants_total: number;
  knowledge_bases_total: number;
  sessions_total: number;
}

export interface SystemSessionCounts {
  active: number;
  awaiting_clarification: number;
  awaiting_review: number;
}

export interface SystemTaskCounts {
  jobs_total: number;
  jobs_pending: number;
  jobs_running: number;
  jobs_failed: number;
  jobs_warning: number;
  jobs_breached: number;
  reviews_total: number;
  reviews_pending: number;
  reviews_escalated: number;
  reviews_warning: number;
  reviews_breached: number;
}

export interface SystemAlert {
  level: string;
  code: string;
  title: string;
  detail: string;
  count?: number | null;
}

export interface SystemReadinessCheck {
  status: string;
  code: string;
  title: string;
  detail: string;
}

export interface SystemReadinessSummary {
  overall_status: string;
  passed: number;
  warnings: number;
  failed: number;
  checks: SystemReadinessCheck[];
}

export interface SystemMaintenanceRequest {
  reconcile_overdue_reviews?: boolean;
  retry_failed_jobs?: boolean;
  job_retry_limit?: number | null;
}

export interface SystemMaintenanceResult {
  executed_at: string;
  reconcile_overdue_reviews_count: number;
  retried_job_count: number;
  retried_job_ids: string[];
  skipped_job_ids: string[];
}

export interface SystemOverview {
  health_status: string;
  summary: SystemSummary;
  runtime: SystemRuntimeOverview;
  resources: SystemResourceCounts;
  sessions: SystemSessionCounts;
  tasks: SystemTaskCounts;
  alerts: SystemAlert[];
  readiness: SystemReadinessSummary;
}

export async function fetchSystemOverview(): Promise<SystemOverview> {
  const response = await apiClient.get<SystemOverview>("/system/overview");
  return response.data;
}

export async function runSystemMaintenance(
  payload: SystemMaintenanceRequest,
): Promise<SystemMaintenanceResult> {
  const response = await apiClient.post<SystemMaintenanceResult>(
    "/system/maintenance/run",
    payload,
  );
  return response.data;
}
