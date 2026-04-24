import { apiClient } from "./client";
import type { TaskSlaSnapshot } from "./taskSla";

export interface JobSummary {
  job_id: string;
  job_type: string;
  target_id: string;
  target_type?: string | null;
  target_name?: string | null;
  knowledge_base_id?: string | null;
  knowledge_base_name?: string | null;
  target_status?: string | null;
  retryable: boolean;
  status: string;
  progress: number;
  error_message: string;
  sla: TaskSlaSnapshot;
  created_at: string;
  updated_at: string;
}

export interface BatchRetryJobsResult {
  requested_count: number;
  retried_count: number;
  skipped_count: number;
  retried_jobs: JobSummary[];
  skipped_job_ids: string[];
}

export async function fetchJobs(params?: {
  job_type?: string;
  status?: string;
  sla_status?: string;
}): Promise<JobSummary[]> {
  const response = await apiClient.get<JobSummary[]>("/jobs", { params });
  return response.data;
}

export async function retryJob(jobId: string): Promise<JobSummary> {
  const response = await apiClient.post<JobSummary>(`/jobs/${jobId}/retry`);
  return response.data;
}

export async function retryJobsBatch(payload: {
  job_ids: string[];
  limit?: number;
}): Promise<BatchRetryJobsResult> {
  const response = await apiClient.post<BatchRetryJobsResult>(
    "/jobs/retry-batch",
    payload,
  );
  return response.data;
}
