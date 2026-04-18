export type ApiMode = 'live' | 'mock';
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
  uploadRagDocument: (payload: {
    source_type: 'telegram_upload';
    source_name: string;
    file: File;
  }) => Promise<RagUploadResponse>;
  deleteRagDocument: (documentId: string) => Promise<{ document_id: string; deleted_at: string }>;
  ping: () => Promise<void>;
};
