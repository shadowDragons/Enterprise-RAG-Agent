import { getStoredAccessToken } from "@/utils/auth";

import { API_BASE_URL, apiClient } from "./client";

export interface ChatCitation {
  chunk_id: string;
  document_id: string;
  knowledge_base_id: string;
  chunk_index: number;
  file_name: string;
  content: string;
  score: number;
}

export interface MessageSummary {
  message_id: string;
  session_id: string;
  role: string;
  content: string;
  citations: ChatCitation[];
  created_at: string;
  updated_at: string;
}

export interface ChatQueryPayload {
  question: string;
  knowledge_base_id?: string;
  knowledge_base_ids?: string[];
  top_k?: number;
}

export interface ChatQueryResponse {
  session_id: string;
  selected_knowledge_base_id: string;
  selected_kb_ids: string[];
  answer: string;
  citations: ChatCitation[];
  retrieval_count: number;
  fallback_reason?: string | null;
  review_id?: string | null;
  review_status?: string | null;
  workflow_trace: Array<{
    node: string;
    detail: string;
  }>;
}

export interface ChatStreamHandlers {
  onStart?: (payload: {
    session_id: string;
    selected_knowledge_base_id: string;
    selected_kb_ids: string[];
    retrieval_count: number;
  }) => void;
  onChunk?: (payload: { delta: string }) => void;
  onCompleted?: (payload: ChatQueryResponse) => void;
  onError?: (payload: { message: string }) => void;
}

export async function fetchSessionMessages(
  sessionId: string,
): Promise<MessageSummary[]> {
  const response = await apiClient.get<MessageSummary[]>(
    `/sessions/${sessionId}/messages`,
  );
  return response.data;
}

export async function streamSessionChat(
  sessionId: string,
  payload: ChatQueryPayload,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const token = getStoredAccessToken();
  const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) {
    let detail = "";
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      try {
        const data = (await response.json()) as { detail?: string };
        if (typeof data.detail === "string") {
          detail = data.detail;
        }
      } catch {
        detail = "";
      }
    }
    throw new Error(detail || `流式请求失败，状态码 ${response.status}`);
  }
  if (!response.body) {
    throw new Error("服务端没有返回流式响应。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  const emitEvent = (block: string) => {
    const lines = block.split(/\r?\n/);
    let event = "message";
    const dataLines: string[] = [];

    for (const line of lines) {
      if (line.startsWith("event:")) {
        event = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trimStart());
      }
    }

    if (dataLines.length === 0) {
      return;
    }

    const eventPayload = JSON.parse(dataLines.join("\n"));
    if (event === "start") {
      handlers.onStart?.(eventPayload);
    } else if (event === "chunk") {
      handlers.onChunk?.(eventPayload);
    } else if (event === "completed") {
      handlers.onCompleted?.(eventPayload);
    } else if (event === "error") {
      handlers.onError?.(eventPayload);
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });

    let separatorIndex = buffer.indexOf("\n\n");
    while (separatorIndex !== -1) {
      const block = buffer.slice(0, separatorIndex).trim();
      buffer = buffer.slice(separatorIndex + 2);
      if (block) {
        emitEvent(block);
      }
      separatorIndex = buffer.indexOf("\n\n");
    }

    if (done) {
      const finalBlock = buffer.trim();
      if (finalBlock) {
        emitEvent(finalBlock);
      }
      break;
    }
  }
}
