import {
  ApiError,
  type AnalyticsReport,
  type ChatListResponse,
  type ChatModeCode,
  type RagDocumentListResponse,
  type RagUploadResponse,
  type SuggestionResponse,
  type SupportApi,
  type TicketListResponse,
  type TicketStatusCode
} from '@/lib/types';

const API_BASE_URL =
  process.env.NEXT_PUBLIC_SUPPORT_API_BASE_URL ?? 'http://127.0.0.1:8081';

type ApiErrorPayload = {
  error?: {
    code?: string;
    message?: string;
  };
  issues?: Array<{
    path: string;
    message: string;
    type?: string;
  }>;
};

function resolveUrl(path: string): string {
  const base = API_BASE_URL.endsWith('/') ? API_BASE_URL.slice(0, -1) : API_BASE_URL;
  const nextPath = path.startsWith('/') ? path : `/${path}`;
  return `${base}${nextPath}`;
}

function buildQuery(params: Record<string, string | number | boolean | undefined>): string {
  const query = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    query.set(key, String(value));
  }

  const text = query.toString();
  return text ? `?${text}` : '';
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const payload = (await response.json()) as ApiErrorPayload;
    const fallbackMessage = `Request failed with ${response.status}`;
    return new ApiError(
      payload.error?.message ?? fallbackMessage,
      response.status,
      payload.error?.code,
      payload.issues
    );
  } catch {
    return new ApiError(`Request failed with ${response.status}`, response.status);
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(resolveUrl(path), {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.headers ?? {})
    },
    cache: 'no-store'
  });

  if (!response.ok) {
    throw await parseError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const supportApi: SupportApi = {
  async ping() {
    await requestJson<TicketListResponse>('/tickets?page=1&page_size=1');
  },

  async listTickets(params) {
    const query = buildQuery({
      page: params?.page ?? 1,
      page_size: params?.page_size ?? 20,
      status_code: params?.status
    });

    return requestJson<TicketListResponse>(`/tickets${query}`);
  },

  async getTicket(ticketId) {
    return requestJson(`/tickets/${ticketId}`);
  },

  async renameTicket(ticketId, title) {
    return requestJson(`/tickets/${ticketId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ title })
    });
  },

  async listChats(params) {
    const query = buildQuery({
      page: params?.page ?? 1,
      page_size: params?.page_size ?? 50,
      mode_code: params?.mode_code
    });

    return requestJson<ChatListResponse>(`/chats${query}`);
  },

  async getChat(chatId) {
    return requestJson(`/chats/${chatId}`);
  },

  async changeChatMode(chatId, payload) {
    return requestJson(`/chats/${chatId}/mode`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });
  },

  async sendMessage(chatId, payload) {
    return requestJson(`/chats/${chatId}/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });
  },

  async getSuggestions(chatId, payload) {
    return requestJson<SuggestionResponse>(`/chats/${chatId}/suggestions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });
  },

  async setDefaultNewTicketMode(mode_code: ChatModeCode) {
    return requestJson<{ mode_code: ChatModeCode; updated_at: string }>(
      '/settings/default-new-ticket-mode',
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ mode_code })
      }
    );
  },

  async listRagDocuments(params) {
    const query = buildQuery({
      page: params?.page ?? 1,
      page_size: params?.page_size ?? 20,
      include_deleted: params?.include_deleted ?? false
    });

    return requestJson<RagDocumentListResponse>(`/rag/documents${query}`);
  },

  async getAnalyticsReport(params) {
    const query = buildQuery({
      from: params?.from,
      to: params?.to
    });

    return requestJson<AnalyticsReport>(`/analytics/report${query}`);
  },

  async uploadRagDocument(payload) {
    const formData = new FormData();
    formData.append('source_type', payload.source_type);
    formData.append('source_name', payload.source_name);
    formData.append('file', payload.file);

    return requestJson<RagUploadResponse>('/rag/documents', {
      method: 'POST',
      body: formData
    });
  },

  async deleteRagDocument(documentId) {
    return requestJson<{ document_id: string; deleted_at: string }>(`/rag/documents/${documentId}`, {
      method: 'DELETE'
    });
  }
};

export const supportLabel = {
  mode(code: ChatModeCode): string {
    if (code === 'full_ai') return 'AI consultant';
    if (code === 'ai_assist') return 'AI assistant';
    return 'No AI';
  },
  status(code: TicketStatusCode): string {
    if (code === 'pending_ai') return 'pending_ai';
    if (code === 'pending_human') return 'pending_human';
    if (code === 'pending_user') return 'pending_user';
    return 'closed';
  }
};
