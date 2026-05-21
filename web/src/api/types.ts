export interface ChatRequest {
  question: string;
  conversation_id?: string | null;
  metadata?: Record<string, unknown>;
}

export interface SqlTable {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  row_count: number;
  truncated: boolean;
}

export interface ChatResponse {
  conversation_id: string | null;
  request_id: string;
  question: string;
  answer: string;
  sql: string | null;
  explanation: string | null;
  confidence: number | null;
  table: SqlTable | null;
  warnings: string[];
  errors: Array<{
    code: string;
    message: string;
    details: Record<string, unknown>;
  }>;
  execution_ms: number | null;
  path?: string | null;
  timings?: Record<string, number> | null;
}

export interface StatusResponse {
  status: "ok" | "degraded";
  app: string;
  version: string;
  profile_id: string;
  profile_ready: boolean;
  agent_ready: boolean;
  memory_ready: boolean;
  tools_ready: boolean;
  llm_ready: boolean;
  errors: string[];
}

export interface ProfileResponse {
  profile_id: string;
  display_name: string;
  dialect: string;
  table_count: number;
  allowed_groups: string[];
}

export interface ToolDescriptor {
  name: string;
  description: string;
  access_groups: string[];
  args_schema: Record<string, unknown>;
}

export interface ToolsListResponse {
  tools: ToolDescriptor[];
}

/** Assistant bubble mirrors structured API fields the UI can render. */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp?: number;
  sql?: string | null;
  table?: SqlTable | null;
  explanation?: string | null;
  confidence?: number | null;
  execution_ms?: number | null;
  warnings?: string[];
  apiErrors?: ChatResponse["errors"];
  path?: string | null;
  timings?: Record<string, number> | null;
}
