import { apiClient } from "./client";
import type { AuditLogEntry } from "./auditLogs";
import type { ChatCitation } from "./chat";
import type { TaskSlaSnapshot } from "./taskSla";

export interface WorkflowTraceStep {
  node: string;
  detail: string;
}

export interface ReviewTaskSummary {
  review_id: string;
  session_id: string;
  session_title: string;
  assistant_id: string;
  assistant_name: string;
  status: "pending" | "approved" | "rejected" | string;
  question: string;
  review_reason: string;
  selected_knowledge_base_id: string;
  selected_kb_ids: string[];
  retrieval_count: number;
  escalation_level: number;
  escalation_reason: string;
  reviewer_note: string;
  final_answer: string;
  sla: TaskSlaSnapshot;
  created_at: string;
  updated_at: string;
  escalated_at?: string | null;
  reviewed_at?: string | null;
}

export interface ReviewTaskDetail extends ReviewTaskSummary {
  pending_message_id: string;
  citations: ChatCitation[];
  workflow_trace: WorkflowTraceStep[];
}

export async function fetchReviewTasks(params?: {
  status?: string;
  session_id?: string;
  sla_status?: string;
}): Promise<ReviewTaskSummary[]> {
  const response = await apiClient.get<ReviewTaskSummary[]>("/reviews", {
    params,
  });
  return response.data;
}

export async function fetchReviewTask(reviewId: string): Promise<ReviewTaskDetail> {
  const response = await apiClient.get<ReviewTaskDetail>(`/reviews/${reviewId}`);
  return response.data;
}

export async function fetchReviewAuditLogs(
  reviewId: string,
  params?: {
    limit?: number;
    event_type?: string;
  },
): Promise<AuditLogEntry[]> {
  const response = await apiClient.get<AuditLogEntry[]>(
    `/reviews/${reviewId}/audit-logs`,
    { params },
  );
  return response.data;
}

export async function approveReviewTask(
  reviewId: string,
  reviewerNote: string,
): Promise<ReviewTaskDetail> {
  const response = await apiClient.post<ReviewTaskDetail>(
    `/reviews/${reviewId}/approve`,
    { reviewer_note: reviewerNote },
  );
  return response.data;
}

export async function rejectReviewTask(
  reviewId: string,
  payload: {
    reviewerNote: string;
    manualAnswer: string;
  },
): Promise<ReviewTaskDetail> {
  const response = await apiClient.post<ReviewTaskDetail>(
    `/reviews/${reviewId}/reject`,
    {
      reviewer_note: payload.reviewerNote,
      manual_answer: payload.manualAnswer,
    },
  );
  return response.data;
}
