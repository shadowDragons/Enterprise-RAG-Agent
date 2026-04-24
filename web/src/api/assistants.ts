import { apiClient } from "./client";

export interface ReviewRuleConfig {
  rule_id: string;
  rule_name: string;
  category: string;
  severity: "low" | "medium" | "high" | "critical";
  priority: number;
  enabled: boolean;
  match_mode: "contains_any" | "contains_all" | "regex";
  keywords: string[];
  regex_pattern: string;
}

export interface AssistantSummary {
  assistant_id: string;
  assistant_name: string;
  description: string;
  system_prompt: string;
  default_model: string;
  default_kb_ids: string[];
  default_kb_count: number;
  session_count: number;
  tool_keys: string[];
  review_enabled: boolean;
  review_rules: ReviewRuleConfig[];
  review_rule_count: number;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface AssistantConfigPayload {
  assistant_name: string;
  description: string;
  system_prompt: string;
  default_model: string;
  default_kb_ids: string[];
  tool_keys: string[];
  review_rules?: ReviewRuleConfig[];
  review_enabled: boolean;
}

export interface CreateAssistantPayload extends AssistantConfigPayload {}

export interface UpdateAssistantPayload extends AssistantConfigPayload {
  change_note: string;
}

export interface AssistantVersionSnapshot extends AssistantConfigPayload {
  review_rules: ReviewRuleConfig[];
  version: number;
}

export interface AssistantVersionSummary {
  assistant_id: string;
  version: number;
  change_note: string;
  created_at: string;
  snapshot: AssistantVersionSnapshot;
}

export interface AssistantVersionDetail extends AssistantVersionSummary {
  assistant_version_id: string;
}

export interface AssistantDeleteResult {
  assistant_id: string;
  deleted_session_count: number;
  deleted_review_count: number;
  deleted_audit_log_count: number;
  deleted_checkpoint_count: number;
}

export async function fetchAssistants(): Promise<AssistantSummary[]> {
  const response = await apiClient.get<AssistantSummary[]>("/assistants");
  return response.data;
}

export async function createAssistant(
  payload: CreateAssistantPayload,
): Promise<AssistantSummary> {
  const response = await apiClient.post<AssistantSummary>("/assistants", payload);
  return response.data;
}

export async function updateAssistant(
  assistantId: string,
  payload: UpdateAssistantPayload,
): Promise<AssistantSummary> {
  const response = await apiClient.put<AssistantSummary>(
    `/assistants/${assistantId}`,
    payload,
  );
  return response.data;
}

export async function fetchAssistantVersions(
  assistantId: string,
): Promise<AssistantVersionSummary[]> {
  const response = await apiClient.get<AssistantVersionSummary[]>(
    `/assistants/${assistantId}/versions`,
  );
  return response.data;
}

export async function fetchAssistantVersionDetail(
  assistantId: string,
  version: number,
): Promise<AssistantVersionDetail> {
  const response = await apiClient.get<AssistantVersionDetail>(
    `/assistants/${assistantId}/versions/${version}`,
  );
  return response.data;
}

export async function restoreAssistantVersion(
  assistantId: string,
  version: number,
  changeNote: string,
): Promise<AssistantSummary> {
  const response = await apiClient.post<AssistantSummary>(
    `/assistants/${assistantId}/versions/${version}/restore`,
    { change_note: changeNote },
  );
  return response.data;
}

export async function deleteAssistant(
  assistantId: string,
): Promise<AssistantDeleteResult> {
  const response = await apiClient.delete<AssistantDeleteResult>(
    `/assistants/${assistantId}`,
  );
  return response.data;
}
