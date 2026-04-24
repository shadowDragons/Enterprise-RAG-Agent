import { apiClient } from "./client";

export interface KnowledgeBaseSummary {
  knowledge_base_id: string;
  knowledge_base_name: string;
  description: string;
  default_retrieval_top_k: number;
  document_count: number;
  assistant_binding_count: number;
  status: string;
}

export interface CreateKnowledgeBasePayload {
  knowledge_base_name: string;
  description: string;
  default_retrieval_top_k: number;
}

export interface UpdateKnowledgeBasePayload extends CreateKnowledgeBasePayload {}

export interface KnowledgeBaseDeleteResult {
  knowledge_base_id: string;
  deleted_document_count: number;
  deleted_chunk_count: number;
  deleted_job_count: number;
  unbound_assistant_count: number;
}

export async function fetchKnowledgeBases(): Promise<KnowledgeBaseSummary[]> {
  const response = await apiClient.get<KnowledgeBaseSummary[]>("/knowledge-bases");
  return response.data;
}

export async function createKnowledgeBase(
  payload: CreateKnowledgeBasePayload,
): Promise<KnowledgeBaseSummary> {
  const response = await apiClient.post<KnowledgeBaseSummary>(
    "/knowledge-bases",
    payload,
  );
  return response.data;
}

export async function updateKnowledgeBase(
  knowledgeBaseId: string,
  payload: UpdateKnowledgeBasePayload,
): Promise<KnowledgeBaseSummary> {
  const response = await apiClient.put<KnowledgeBaseSummary>(
    `/knowledge-bases/${knowledgeBaseId}`,
    payload,
  );
  return response.data;
}

export async function deleteKnowledgeBase(
  knowledgeBaseId: string,
): Promise<KnowledgeBaseDeleteResult> {
  const response = await apiClient.delete<KnowledgeBaseDeleteResult>(
    `/knowledge-bases/${knowledgeBaseId}`,
  );
  return response.data;
}
