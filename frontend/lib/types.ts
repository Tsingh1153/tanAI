// Shared API types mirroring the backend Pydantic schemas.

export type Role = "user" | "assistant" | "system";

export interface RetrievedSource {
  document_id: string;
  filename: string;
  locator?: string | null;
  score: number;
  snippet: string;
}

export interface WebSource {
  title: string;
  url: string;
  snippet: string;
}

export interface MemoryInfo {
  id: string;
  kind: string;
  content: string;
  importance: number;
  pinned: boolean;
  use_count: number;
  source_conversation_id?: string | null;
  created_at: string;
  last_used_at?: string | null;
  expires_at?: string | null;
}

export interface AgentStep {
  tool: string;
  arguments: Record<string, unknown>;
  output?: string;
  status: "running" | "done" | "denied";
}

export interface Message {
  id: string;
  role: Role;
  content: string;
  model?: string | null;
  created_at: string;
  // Image URLs (served /images/...) or data URLs (optimistic) attached to a turn.
  images?: string[];
  // Attached at render time for assistant turns produced with RAG.
  sources?: RetrievedSource[];
  // Web search citations for this turn.
  webSources?: WebSource[];
  // Long-term memories recalled for this turn.
  memories?: MemoryInfo[];
  // Agent tool-use timeline for this turn.
  steps?: AgentStep[];
}

export interface PendingApproval {
  tool: string;
  arguments: Record<string, unknown>;
}

export interface DocumentInfo {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  num_chunks: number;
  status: "indexing" | "ready" | "error";
  error?: string | null;
  // null => promoted to global "memory"; otherwise pinned to that chat.
  conversation_id?: string | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  model: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationWithMessages extends Conversation {
  messages: Message[];
}

export interface ModelInfo {
  name: string;
  provider: string;
  provider_label: string;
  size?: number | null;
  modified_at?: string | null;
}

export interface ProviderInfo {
  name: string;
  label: string;
  kind: string;
  base_url?: string | null;
  online: boolean;
  has_api_key: boolean;
  removable: boolean;
}

export interface MCPServerInfo {
  name: string;
  command: string;
  connected: boolean;
  error?: string | null;
  tools: string[];
}

export interface PluginInfo {
  loaded: string[];
  errors: Record<string, string>;
  tools: string[];
}

export interface Health {
  status: string;
  provider: string;
  provider_online: boolean;
  default_model: string;
  embedding_model: string;
  embedding_online: boolean;
  indexed_chunks: number;
  hardware: string;
}

// WebSocket streaming protocol events emitted by the backend.
export type StreamEvent =
  | { type: "start" }
  | { type: "sources"; data: RetrievedSource[] }
  | { type: "web_sources"; data: WebSource[] }
  | { type: "memory"; data: MemoryInfo[] }
  | {
      type: "tool_call";
      tool: string;
      arguments: Record<string, unknown>;
      requires_approval: boolean;
    }
  | { type: "tool_result"; tool: string; output: string; denied?: boolean }
  | {
      type: "approval_request";
      tool: string;
      arguments: Record<string, unknown>;
    }
  | { type: "token"; data: string }
  | { type: "done" }
  | { type: "error"; detail: string };

export interface SendOptions {
  model?: string;
  provider?: string;
  useRag?: boolean;
  documentIds?: string[];
  useMemory?: boolean;
  useWeb?: boolean;
  agent?: boolean;
  images?: string[]; // data URLs
  regenerate?: boolean; // re-run without persisting a new user turn
}
