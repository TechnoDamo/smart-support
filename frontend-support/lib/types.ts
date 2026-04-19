export type ThemeMode = 'system' | 'light' | 'dark';

export type TicketStatusCode = 'pending_ai' | 'pending_human' | 'pending_user' | 'closed';
export type ChatModeCode = 'full_ai' | 'no_ai' | 'ai_assist';
export type ActorEntity = 'user' | 'operator' | 'ai_operator';

export type PagingResponse<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
};

export type Channel = {
  id: string;
  code: string;
  name: string;
};

export type Ticket = {
  id: string;
  title?: string;
  summary?: string | null;
  status_code: TicketStatusCode;
  chat_id: string;
  time_started: string;
  time_closed?: string | null;
};

export type TicketStatusEvent = {
  from_status_code?: TicketStatusCode | null;
  to_status_code: TicketStatusCode;
  changed_by: ActorEntity;
  changed_by_user_id?: string | null;
  reason?: string | null;
  created_at: string;
};

export type TicketDetails = Ticket & {
  status_events?: TicketStatusEvent[];
};

export type TicketListResponse = PagingResponse<Ticket>;

export type Chat = {
  id: string;
  telegram_chat_id: number;
  user_id: string;
  channel: Channel;
  mode_code: ChatModeCode;
  active_ticket_id?: string | null;
  updated_at: string;
};

export type ChatModeEvent = {
  from_mode_code?: ChatModeCode | null;
  to_mode_code: ChatModeCode;
  changed_by: ActorEntity;
  changed_by_user_id?: string | null;
  reason?: string | null;
  created_at: string;
};

export type Message = {
  id: string;
  chat_id: string;
  ticket_id: string;
  entity: ActorEntity;
  seq: number;
  text: string;
  time: string;
};

export type ChatDetails = Chat & {
  mode_events?: ChatModeEvent[];
  messages?: Message[];
};

export type ChatListResponse = PagingResponse<Chat>;

export type SuggestionCitation = {
  chunk_id: string;
  document_id: string;
  score: number;
};

export type Suggestion = {
  id: string;
  text: string;
  confidence?: number | null;
  citations?: SuggestionCitation[];
};

export type SuggestionResponse = {
  suggestions: Suggestion[];
};

export type RagDocument = {
  id: string;
  collection_id: string;
  source_type: string;
  source_name: string;
  current_version: number;
  created_at: string;
  deleted_at?: string | null;
};

export type RagDocumentListResponse = PagingResponse<RagDocument>;

export type RagUploadResponse = {
  document_id: string;
  ingestion_job_id: string;
  status: 'queued' | 'processing' | 'done' | 'failed';
};

export type AnalyticsPeriod = {
  from: string;
  to: string;
};

export type AnalyticsTickets = {
  total: number;
  by_status: {
    pending_ai: number;
    pending_human: number;
    closed: number;
  };
  opened_in_period: number;
  closed_in_period: number;
  avg_resolution_time_seconds?: number | null;
  resolution_time_p50_seconds?: number | null;
  resolution_time_p95_seconds?: number | null;
};

export type AnalyticsMessages = {
  total: number;
  in_period: number;
  by_entity: {
    user: number;
    ai_operator: number;
    operator: number;
  };
  avg_per_ticket?: number | null;
};

export type AnalyticsAiPerformance = {
  tickets_closed_by_ai: number;
  tickets_escalated_to_human: number;
  resolution_rate: number;
  escalation_rate: number;
  avg_messages_before_escalation?: number | null;
  chat_mode_distribution: {
    full_ai: number;
    ai_assist: number;
    no_ai: number;
  };
};

export type AnalyticsRag = {
  total_documents: number;
  active_documents: number;
  deleted_documents: number;
  total_chunks: number;
  ingestion_jobs: {
    queued: number;
    processing: number;
    done: number;
    failed: number;
  };
  retrieval: {
    total_events: number;
    events_in_period: number;
    avg_score?: number | null;
    hit_rate?: number | null;
  };
};

export type AnalyticsUsers = {
  total: number;
  new_in_period: number;
  returning_users_in_period: number;
  avg_tickets_per_user?: number | null;
};

export type AnalyticsReport = {
  generated_at: string;
  period: AnalyticsPeriod;
  tickets: AnalyticsTickets;
  messages: AnalyticsMessages;
  ai_performance: AnalyticsAiPerformance;
  rag: AnalyticsRag;
  users: AnalyticsUsers;
};

export type ValidationIssue = {
  path: string;
  message: string;
  type?: string;
};

export class ApiError extends Error {
  status: number;
  code?: string;
  issues?: ValidationIssue[];

  constructor(message: string, status: number, code?: string, issues?: ValidationIssue[]) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.issues = issues;
  }
}

export type ServerStatus = 'unknown' | 'online' | 'offline';

// Graylog Log Entry Types
export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';

export type GraylogLogEntry = {
  timestamp: string;
  level: LogLevel;
  logger: string;
  message: string;
  service: string;
  environment: string;
  request_id?: string;
  user_id?: string;
  endpoint?: string;
  method?: string;
  status_code?: number;
  duration_ms?: number;
  db_operation?: string;
  db_table?: string;
  db_duration_ms?: number;
  error_type?: string;
  stack_trace?: string;
  [key: string]: any;
};

export type GraylogLogResponse = {
  logs: GraylogLogEntry[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
};

export type GraylogStats = {
  total_logs: number;
  logs_by_level: Record<LogLevel, number>;
  logs_by_service: Record<string, number>;
  logs_by_endpoint: Record<string, number>;
  error_rate: number;
  avg_response_time_ms: number;
  top_endpoints: Array<{ endpoint: string; count: number; avg_duration_ms: number }>;
  recent_errors: GraylogLogEntry[];
};

export type GraylogSettings = {
  enabled: boolean;
  host: string;
  port: number;
  protocol: 'tcp' | 'udp';
  web_ui_url: string;
  username: string;
  password: string;
};

export type SupportApi = {
  listTickets: (params?: {
    page?: number;
    page_size?: number;
    status?: TicketStatusCode;
  }) => Promise<TicketListResponse>;
  getTicket: (ticketId: string) => Promise<TicketDetails>;
  renameTicket: (ticketId: string, title: string) => Promise<{ id: string; title: string; updated_at: string }>;
  listChats: (params?: {
    page?: number;
    page_size?: number;
    mode_code?: ChatModeCode;
  }) => Promise<ChatListResponse>;
  getChat: (chatId: string) => Promise<ChatDetails>;
  changeChatMode: (
    chatId: string,
    payload: { to_mode_code: ChatModeCode; reason?: string }
  ) => Promise<{ chat_id: string; mode_code: ChatModeCode; changed_at: string }>;
  sendMessage: (chatId: string, payload: { ticket_id: string; text: string }) => Promise<Message>;
  getSuggestions: (
    chatId: string,
    payload: { ticket_id: string; draft_context?: string; max_suggestions?: number }
  ) => Promise<SuggestionResponse>;
  setDefaultNewTicketMode: (mode_code: ChatModeCode) => Promise<{ mode_code: ChatModeCode; updated_at: string }>;
  listRagDocuments: (params?: {
    page?: number;
    page_size?: number;
    include_deleted?: boolean;
  }) => Promise<RagDocumentListResponse>;
  getAnalyticsReport: (params?: {
    from?: string;
    to?: string;
  }) => Promise<AnalyticsReport>;
  uploadRagDocument: (payload: {
    source_type: 'telegram_upload';
    source_name: string;
    file: File;
  }) => Promise<RagUploadResponse>;
  deleteRagDocument: (documentId: string) => Promise<{ document_id: string; deleted_at: string }>;
  ping: () => Promise<void>;
  // Graylog API methods
  getGraylogLogs: (params?: {
    page?: number;
    page_size?: number;
    level?: LogLevel;
    service?: string;
    endpoint?: string;
    search?: string;
    from?: string;
    to?: string;
  }) => Promise<GraylogLogResponse>;
  getGraylogStats: (params?: {
    from?: string;
    to?: string;
  }) => Promise<GraylogStats>;
  getGraylogSettings: () => Promise<GraylogSettings>;
  updateGraylogSettings: (settings: Partial<GraylogSettings>) => Promise<GraylogSettings>;
  testGraylogConnection: () => Promise<{ connected: boolean; message: string }>;
};
