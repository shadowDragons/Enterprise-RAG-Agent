export interface AuditLogEntry {
  audit_log_id: string;
  assistant_id: string;
  session_id: string;
  review_id?: string | null;
  workflow_thread_id: string;
  event_type: string;
  event_level: string;
  summary: string;
  detail_payload: Record<string, unknown>;
  created_at: string;
}
