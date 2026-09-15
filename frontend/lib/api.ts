// Typed REST client for the backend — all network access flows through here.

import type {
  Conversation,
  ConversationWithMessages,
  DocumentInfo,
  Folder,
  Health,
  MCPServerInfo,
  MemoryInfo,
  ModelInfo,
  Persona,
  PluginInfo,
  ProviderInfo,
  RetrievedSource,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

/** Derive the WebSocket origin from the HTTP base URL. */
export function wsBase(): string {
  return API_BASE.replace(/^http/, "ws");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON error body; keep status text */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/health"),

  listModels: () => request<ModelInfo[]>("/api/models"),

  listPersonas: () => request<Persona[]>("/api/personas"),

  listConversations: () => request<Conversation[]>("/api/conversations"),

  getConversation: (id: string) =>
    request<ConversationWithMessages>(`/api/conversations/${id}`),

  createConversation: (model?: string) =>
    request<ConversationWithMessages>("/api/conversations", {
      method: "POST",
      body: JSON.stringify({ model }),
    }),

  updateConversation: (
    id: string,
    patch: {
      title?: string;
      model?: string;
      pinned?: boolean;
      folder_id?: string | null;
    },
  ) =>
    request<Conversation>(`/api/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  listFolders: () => request<Folder[]>("/api/folders"),

  createFolder: (name: string) =>
    request<Folder>("/api/folders", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  renameFolder: (id: string, name: string) =>
    request<Folder>(`/api/folders/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),

  deleteFolder: (id: string) =>
    request<void>(`/api/folders/${id}`, { method: "DELETE" }),

  deleteConversation: (id: string) =>
    request<void>(`/api/conversations/${id}`, { method: "DELETE" }),

  // Delete a message and everything after it (for edit / regenerate).
  truncateFrom: (conversationId: string, messageId: string) =>
    request<void>(
      `/api/conversations/${conversationId}/messages/${messageId}`,
      { method: "DELETE" },
    ),

  listDocuments: (conversationId?: string) =>
    request<DocumentInfo[]>(
      "/api/documents" +
        (conversationId
          ? `?conversation_id=${encodeURIComponent(conversationId)}`
          : ""),
    ),

  // Uploads use multipart/form-data, so we bypass the JSON `request` helper.
  uploadDocument: async (
    file: File,
    conversationId?: string,
  ): Promise<DocumentInfo> => {
    const form = new FormData();
    form.append("file", file);
    if (conversationId) form.append("conversation_id", conversationId);
    const res = await fetch(`${API_BASE}/api/documents`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        detail = (await res.json()).detail ?? detail;
      } catch {
        /* keep status text */
      }
      throw new Error(detail);
    }
    return (await res.json()) as DocumentInfo;
  },

  promoteDocument: (id: string) =>
    request<DocumentInfo>(`/api/documents/${id}/memory`, { method: "POST" }),

  deleteDocument: (id: string) =>
    request<void>(`/api/documents/${id}`, { method: "DELETE" }),

  search: (query: string, top_k = 5) =>
    request<{ results: RetrievedSource[] }>("/api/search", {
      method: "POST",
      body: JSON.stringify({ query, top_k }),
    }),

  listMemories: () => request<MemoryInfo[]>("/api/memories"),

  createMemory: (content: string, kind = "fact", pinned = false) =>
    request<MemoryInfo>("/api/memories", {
      method: "POST",
      body: JSON.stringify({ content, kind, pinned }),
    }),

  updateMemory: (
    id: string,
    patch: {
      content?: string;
      kind?: string;
      pinned?: boolean;
      importance?: number;
    },
  ) =>
    request<MemoryInfo>(`/api/memories/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  deleteMemory: (id: string) =>
    request<void>(`/api/memories/${id}`, { method: "DELETE" }),

  listProviders: () => request<ProviderInfo[]>("/api/providers"),

  addProvider: (payload: {
    label: string;
    base_url: string;
    api_key?: string;
  }) =>
    request<ProviderInfo>("/api/providers", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  deleteProvider: (name: string) =>
    request<void>(`/api/providers/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),

  deleteModel: (name: string) =>
    request<void>(`/api/models?name=${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),

  // Returns the SSE URL for streaming a model pull's progress.
  pullModelUrl: (name: string) =>
    `${API_BASE}/api/models/pull?name=${encodeURIComponent(name)}`,

  listPlugins: () => request<PluginInfo>("/api/plugins"),

  listMcpServers: () => request<MCPServerInfo[]>("/api/mcp"),

  addMcpServer: (payload: {
    name: string;
    command: string;
    args: string[];
    env?: Record<string, string>;
  }) =>
    request<MCPServerInfo>("/api/mcp", {
      method: "POST",
      body: JSON.stringify({ env: {}, ...payload }),
    }),

  deleteMcpServer: (name: string) =>
    request<void>(`/api/mcp/${encodeURIComponent(name)}`, { method: "DELETE" }),

  fmQuota: () =>
    request<{ available: boolean; output: string }>("/api/fm/quota"),

  generateImages: (prompt: string, n = 1) =>
    request<{ images: string[] }>("/api/images/generate", {
      method: "POST",
      body: JSON.stringify({ prompt, n }),
    }),

  // Transcribe an audio blob to text via local Whisper (multipart upload).
  transcribe: async (
    blob: Blob,
  ): Promise<{ text: string; language: string }> => {
    const form = new FormData();
    form.append("file", blob, "clip.webm");
    const res = await fetch(`${API_BASE}/api/transcribe`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        detail = (await res.json()).detail ?? detail;
      } catch {
        /* keep status text */
      }
      throw new Error(detail);
    }
    return res.json();
  },
};
