import { apiClient } from "./client";
import type { AuditLogEntry } from "./auditLogs";

export interface SessionWorkflowRuntime {
  runtime_schema_version?: number | null;
  runtime_state?: string | null;
  runtime_label?: string | null;
  current_goal?: string | null;
  resolved_question?: string | null;
  pending_question?: string | null;
  clarification_type?: string | null;
  clarification_stage?: string | null;
  clarification_expected_input?: string | null;
  clarification_reason?: string | null;
  pending_review_id?: string | null;
  pending_review_reason?: string | null;
  pending_review_status?: string | null;
  pending_review_escalation_reason?: string | null;
  pending_review_escalated_at?: string | null;
  runtime_reason?: string | null;
  waiting_for?: string | null;
  resume_strategy?: string | null;
  latest_node?: string | null;
  latest_node_detail?: string | null;
  workflow_thread_id?: string | null;
  workflow_checkpoint_id?: string | null;
  workflow_checkpoint_updated_at?: string | null;
  workflow_source?: string | null;
  workflow_step?: number | null;
  workflow_checkpoint_backend?: string | null;
  workflow_checkpoint_backend_label?: string | null;
  checkpoint_status?: string | null;
  checkpoint_label?: string | null;
  workflow_pending_write_count?: number | null;
  workflow_can_resume?: boolean | null;
}

export interface SessionSummary {
  session_id: string;
  assistant_id: string;
  assistant_name: string;
  title: string;
  status: string;
  message_count: number;
  workflow_runtime?: SessionWorkflowRuntime | null;
  created_at: string;
  updated_at: string;
}

export interface CreateSessionPayload {
  assistant_id: string;
  title: string;
}

export interface SessionDeleteResult {
  session_id: string;
  assistant_id: string;
  deleted_message_count: number;
  deleted_review_count: number;
  deleted_audit_log_count: number;
  deleted_checkpoint_count: number;
}

export async function fetchSessions(params?: {
  assistant_id?: string;
}): Promise<SessionSummary[]> {
  const response = await apiClient.get<SessionSummary[]>("/sessions", { params });
  return response.data;
}

export async function createSession(
  payload: CreateSessionPayload,
): Promise<SessionSummary> {
  const response = await apiClient.post<SessionSummary>("/sessions", payload);
  return response.data;
}

export async function fetchSession(sessionId: string): Promise<SessionSummary> {
  const response = await apiClient.get<SessionSummary>(`/sessions/${sessionId}`);
  return response.data;
}

export async function fetchSessionAuditLogs(
  sessionId: string,
  params?: {
    limit?: number;
    event_type?: string;
  },
): Promise<AuditLogEntry[]> {
  const response = await apiClient.get<AuditLogEntry[]>(
    `/sessions/${sessionId}/audit-logs`,
    { params },
  );
  return response.data;
}

export async function deleteSession(
  sessionId: string,
): Promise<SessionDeleteResult> {
  const response = await apiClient.delete<SessionDeleteResult>(`/sessions/${sessionId}`);
  return response.data;
}
