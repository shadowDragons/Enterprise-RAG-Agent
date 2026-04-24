import { apiClient } from "./client";

export interface DocumentSummary {
  document_id: string;
  knowledge_base_id: string;
  file_name: string;
  mime_type: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface DocumentUploadAccepted {
  document: DocumentSummary;
  job: {
    job_id: string;
    job_type: string;
    target_id: string;
    status: string;
    progress: number;
    error_message: string;
    created_at: string;
    updated_at: string;
  };
}

export interface DocumentDeleteResult {
  document_id: string;
  knowledge_base_id: string;
  deleted_chunk_count: number;
  deleted_job_count: number;
}

export async function fetchDocuments(
  knowledgeBaseId: string,
): Promise<DocumentSummary[]> {
  const response = await apiClient.get<DocumentSummary[]>(
    `/knowledge-bases/${knowledgeBaseId}/documents`,
  );
  return response.data;
}

export async function deleteDocument(
  knowledgeBaseId: string,
  documentId: string,
): Promise<DocumentDeleteResult> {
  const response = await apiClient.delete<DocumentDeleteResult>(
    `/knowledge-bases/${knowledgeBaseId}/documents/${documentId}`,
  );
  return response.data;
}

export async function uploadDocument(
  knowledgeBaseId: string,
  file: File,
): Promise<DocumentUploadAccepted> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiClient.post<DocumentUploadAccepted>(
    `/knowledge-bases/${knowledgeBaseId}/documents/upload`,
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    },
  );
  return response.data;
}
