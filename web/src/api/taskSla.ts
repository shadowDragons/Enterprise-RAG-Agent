export interface TaskSlaSnapshot {
  policy_key: string;
  policy_name: string;
  status: "normal" | "warning" | "breached" | "completed" | "failed" | string;
  target_seconds: number;
  warning_seconds: number;
  elapsed_seconds: number;
  remaining_seconds: number;
  breach_seconds: number;
  deadline_at: string;
  resolved_at?: string | null;
  resolution_seconds?: number | null;
  target_met?: boolean | null;
}
