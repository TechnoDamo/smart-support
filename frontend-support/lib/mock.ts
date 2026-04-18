import {
  type ChatDetails,
  type ChatModeCode,
  type Message,
  type RagDocument,
  type Suggestion,
  type SupportApi,
  type TicketDetails,
  type TicketStatusCode
} from '@/lib/types';

function uid() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function nowIso() {
  return new Date().toISOString();
}

function minutesAgo(minutes: number) {
  return new Date(Date.now() - minutes * 60_000).toISOString();
}

function paginate<T>(items: T[], page: number, pageSize: number) {
  const start = (page - 1) * pageSize;
  const end = start + pageSize;
  return {
    items: items.slice(start, end),
    page,
    page_size: pageSize,
    total: items.length
  };
}

type MockState = {
  tickets: TicketDetails[];
  chats: ChatDetails[];
  ragDocs: RagDocument[];
  defaultMode: ChatModeCode;
  globalSeq: number;
  lastAutoActivityAt: number;
};

const channelTelegram = {
  id: uid(),
  code: 'telegram',
  name: 'Telegram'
};

const channelMax = {
  id: uid(),
  code: 'max',
  name: 'MAX'
};

const chatAId = uid();
const chatBId = uid();
const chatCId = uid();

const ticketAId = uid();
const ticketBId = uid();
const ticketCId = uid();

const state: MockState = {
  tickets: [
    {
      id: ticketAId,
      title: 'Проблема с оплатой подписки',
      summary: null,
      status_code: 'pending_human',
      chat_id: chatAId,
      time_started: minutesAgo(44),
      time_closed: null,
      status_events: [
        {
          from_status_code: null,
          to_status_code: 'pending_ai',
          changed_by: 'ai_operator',
          reason: 'ticket_created',
          created_at: minutesAgo(44)
        },
        {
          from_status_code: 'pending_ai',
          to_status_code: 'pending_human',
          changed_by: 'operator',
          reason: 'manual_handoff',
          created_at: minutesAgo(21)
        }
      ]
    },
    {
      id: ticketBId,
      title: 'Как восстановить пароль?',
      summary: null,
      status_code: 'pending_ai',
      chat_id: chatBId,
      time_started: minutesAgo(17),
      time_closed: null,
      status_events: [
        {
          from_status_code: null,
          to_status_code: 'pending_ai',
          changed_by: 'ai_operator',
          reason: 'ticket_created',
          created_at: minutesAgo(17)
        }
      ]
    },
    {
      id: ticketCId,
      title: 'Проверка тарифов',
      summary: 'Пользователь получил ответ и тикет закрыт автоматически по таймауту.',
      status_code: 'closed',
      chat_id: chatCId,
      time_started: minutesAgo(280),
      time_closed: minutesAgo(210),
      status_events: [
        {
          from_status_code: null,
          to_status_code: 'pending_ai',
          changed_by: 'ai_operator',
          reason: 'ticket_created',
          created_at: minutesAgo(280)
        },
        {
          from_status_code: 'pending_ai',
          to_status_code: 'closed',
          changed_by: 'ai_operator',
          reason: 'auto_close',
          created_at: minutesAgo(210)
        }
      ]
    }
  ],
  chats: [
    {
      id: chatAId,
      telegram_chat_id: 990_001,
      user_id: uid(),
      channel: channelTelegram,
      mode_code: 'no_ai',
      active_ticket_id: ticketAId,
      updated_at: minutesAgo(3),
      mode_events: [
        {
          from_mode_code: null,
          to_mode_code: 'ai_assist',
          changed_by: 'operator',
          reason: 'default_new_ticket_mode',
          created_at: minutesAgo(44)
        },
        {
          from_mode_code: 'ai_assist',
          to_mode_code: 'no_ai',
          changed_by: 'operator',
          reason: 'handoff_to_human',
          created_at: minutesAgo(21)
        }
      ],
      messages: [
        {
          id: uid(),
          chat_id: chatAId,
          ticket_id: ticketAId,
          entity: 'user',
          seq: 1,
          text: 'Здравствуйте, списались деньги два раза.',
          time: minutesAgo(44)
        },
        {
          id: uid(),
          chat_id: chatAId,
          ticket_id: ticketAId,
          entity: 'ai_operator',
          seq: 2,
          text: 'Понимаю. Передал диалог оператору для проверки.',
          time: minutesAgo(43)
        },
        {
          id: uid(),
          chat_id: chatAId,
          ticket_id: ticketAId,
          entity: 'operator',
          seq: 3,
          text: 'Проверяю платеж, подскажите последние 4 цифры карты.',
          time: minutesAgo(21)
        },
        {
          id: uid(),
          chat_id: chatAId,
          ticket_id: ticketAId,
          entity: 'user',
          seq: 4,
          text: '4821',
          time: minutesAgo(3)
        }
      ]
    },
    {
      id: chatBId,
      telegram_chat_id: 990_002,
      user_id: uid(),
      channel: channelMax,
      mode_code: 'full_ai',
      active_ticket_id: ticketBId,
      updated_at: minutesAgo(2),
      mode_events: [
        {
          from_mode_code: null,
          to_mode_code: 'full_ai',
          changed_by: 'operator',
          reason: 'default_new_ticket_mode',
          created_at: minutesAgo(17)
        }
      ],
      messages: [
        {
          id: uid(),
          chat_id: chatBId,
          ticket_id: ticketBId,
          entity: 'user',
          seq: 5,
          text: 'Не могу войти в аккаунт после смены телефона.',
          time: minutesAgo(17)
        },
        {
          id: uid(),
          chat_id: chatBId,
          ticket_id: ticketBId,
          entity: 'ai_operator',
          seq: 6,
          text: 'Попробуйте восстановить пароль через форму “Забыли пароль?”.',
          time: minutesAgo(15)
        },
        {
          id: uid(),
          chat_id: chatBId,
          ticket_id: ticketBId,
          entity: 'user',
          seq: 7,
          text: 'Не пришло письмо, что делать?',
          time: minutesAgo(2)
        }
      ]
    },
    {
      id: chatCId,
      telegram_chat_id: 990_003,
      user_id: uid(),
      channel: channelTelegram,
      mode_code: 'ai_assist',
      active_ticket_id: null,
      updated_at: minutesAgo(210),
      mode_events: [
        {
          from_mode_code: null,
          to_mode_code: 'ai_assist',
          changed_by: 'operator',
          reason: 'default_new_ticket_mode',
          created_at: minutesAgo(280)
        }
      ],
      messages: [
        {
          id: uid(),
          chat_id: chatCId,
          ticket_id: ticketCId,
          entity: 'user',
          seq: 8,
          text: 'Какая цена годового тарифа?',
          time: minutesAgo(280)
        },
        {
          id: uid(),
          chat_id: chatCId,
          ticket_id: ticketCId,
          entity: 'ai_operator',
          seq: 9,
          text: 'Сейчас действует скидка, отправляю актуальные цены.',
          time: minutesAgo(279)
        }
      ]
    }
  ],
  ragDocs: [
    {
      id: uid(),
      collection_id: uid(),
      source_type: 'telegram_upload',
      source_name: 'billing_faq.md',
      current_version: 3,
      created_at: minutesAgo(500),
      deleted_at: null
    },
    {
      id: uid(),
      collection_id: uid(),
      source_type: 'telegram_upload',
      source_name: 'security_policy.pdf',
      current_version: 1,
      created_at: minutesAgo(430),
      deleted_at: null
    }
  ],
  defaultMode: 'ai_assist',
  globalSeq: 9,
  lastAutoActivityAt: Date.now()
};

function getTicketById(ticketId: string) {
  const ticket = state.tickets.find((item) => item.id === ticketId);
  if (!ticket) {
    throw new Error('Ticket not found');
  }
  return ticket;
}

function getChatById(chatId: string) {
  const chat = state.chats.find((item) => item.id === chatId);
  if (!chat) {
    throw new Error('Chat not found');
  }
  return chat;
}

function modeToTicketStatus(mode: ChatModeCode, fallback: TicketStatusCode): TicketStatusCode {
  if (mode === 'no_ai') return 'pending_human';
  if (mode === 'ai_assist' || mode === 'full_ai') return 'pending_ai';
  return fallback;
}

function maybeGenerateIncomingActivity() {
  const elapsed = Date.now() - state.lastAutoActivityAt;
  if (elapsed < 12_000) return;

  const openTickets = state.tickets.filter((item) => item.status_code !== 'closed');
  if (!openTickets.length) return;

  state.lastAutoActivityAt = Date.now();
  const ticket = openTickets[Math.floor(Math.random() * openTickets.length)];
  const chat = getChatById(ticket.chat_id);

  const incomingTexts = [
    'Спасибо, вижу ответ. Что дальше?',
    'Можете уточнить, сколько это займет?',
    'Проверил, пока не сработало.',
    'Подскажите, это точно безопасно?'
  ];

  const userMessage: Message = {
    id: uid(),
    chat_id: chat.id,
    ticket_id: ticket.id,
    entity: 'user',
    seq: ++state.globalSeq,
    text: incomingTexts[Math.floor(Math.random() * incomingTexts.length)],
    time: nowIso()
  };

  chat.messages = [...(chat.messages ?? []), userMessage];
  chat.updated_at = userMessage.time;

  if (chat.mode_code === 'full_ai') {
    const aiReplies = [
      'Понял вас. Проверяю актуальный сценарий и скоро вернусь с шагами.',
      'Спасибо за уточнение. Уже подбираю точный ответ по базе знаний.',
      'Принял. Сейчас сформирую инструкцию и отправлю одним сообщением.'
    ];

    const aiMessage: Message = {
      id: uid(),
      chat_id: chat.id,
      ticket_id: ticket.id,
      entity: 'ai_operator',
      seq: ++state.globalSeq,
      text: aiReplies[Math.floor(Math.random() * aiReplies.length)],
      time: nowIso()
    };

    chat.messages = [...(chat.messages ?? []), aiMessage];
    chat.updated_at = aiMessage.time;
  }
}

function toSuggestionText(base: string): Suggestion[] {
  const docs = state.ragDocs.filter((item) => !item.deleted_at);

  return Array.from({ length: 3 }).map((_, index) => ({
    id: uid(),
    text:
      index === 0
        ? `Спасибо за уточнение. ${base} Сначала проверим настройки уведомлений и папку спам.`
        : index === 1
          ? `Могу предложить быстрый шаг: ${base.toLowerCase()} После этого проверим альтернативный контакт.`
          : `Если проблема сохранится, зафиксирую кейс и передам в ручную проверку. Пока попробуйте: ${base}.`,
    confidence: Number((0.74 - index * 0.08).toFixed(2)),
    citations: docs.slice(0, 2).map((doc, citationIndex) => ({
      chunk_id: uid(),
      document_id: doc.id,
      score: Number((0.92 - citationIndex * 0.09).toFixed(2))
    }))
  }));
}

export const supportMockApi: SupportApi = {
  async ping() {
    await wait(120);
  },

  async listTickets(params) {
    await wait(160);
    maybeGenerateIncomingActivity();

    const page = params?.page ?? 1;
    const pageSize = params?.page_size ?? 20;

    let items = [...state.tickets];
    if (params?.status) {
      items = items.filter((item) => item.status_code === params.status);
    }

    items.sort((a, b) => {
      const ta = new Date(a.time_closed ?? a.time_started).getTime();
      const tb = new Date(b.time_closed ?? b.time_started).getTime();
      return tb - ta;
    });

    return paginate(items, page, pageSize);
  },

  async getTicket(ticketId) {
    await wait(110);
    maybeGenerateIncomingActivity();
    return structuredClone(getTicketById(ticketId));
  },

  async renameTicket(ticketId, title) {
    await wait(120);
    const ticket = getTicketById(ticketId);
    ticket.title = title;
    return {
      id: ticket.id,
      title,
      updated_at: nowIso()
    };
  },

  async listChats(params) {
    await wait(150);
    maybeGenerateIncomingActivity();

    const page = params?.page ?? 1;
    const pageSize = params?.page_size ?? 50;

    let items = [...state.chats];
    if (params?.mode_code) {
      items = items.filter((item) => item.mode_code === params.mode_code);
    }

    items.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());

    return paginate(
      items.map((chat) => ({
        id: chat.id,
        telegram_chat_id: chat.telegram_chat_id,
        user_id: chat.user_id,
        channel: chat.channel,
        mode_code: chat.mode_code,
        active_ticket_id: chat.active_ticket_id,
        updated_at: chat.updated_at
      })),
      page,
      pageSize
    );
  },

  async getChat(chatId) {
    await wait(110);
    maybeGenerateIncomingActivity();
    return structuredClone(getChatById(chatId));
  },

  async changeChatMode(chatId, payload) {
    await wait(130);
    const chat = getChatById(chatId);
    const previousMode = chat.mode_code;
    chat.mode_code = payload.to_mode_code;
    const changedAt = nowIso();
    chat.updated_at = changedAt;
    chat.mode_events = [
      ...(chat.mode_events ?? []),
      {
        from_mode_code: previousMode,
        to_mode_code: payload.to_mode_code,
        changed_by: 'operator',
        reason: payload.reason ?? null,
        created_at: changedAt,
        changed_by_user_id: null
      }
    ];

    if (chat.active_ticket_id) {
      const ticket = getTicketById(chat.active_ticket_id);
      const prevStatus = ticket.status_code;
      const nextStatus = modeToTicketStatus(payload.to_mode_code, prevStatus);
      if (prevStatus !== nextStatus && prevStatus !== 'closed') {
        ticket.status_code = nextStatus;
        ticket.status_events = [
          ...(ticket.status_events ?? []),
          {
            from_status_code: prevStatus,
            to_status_code: nextStatus,
            changed_by: 'operator',
            reason: payload.reason ?? 'mode_change',
            created_at: changedAt,
            changed_by_user_id: null
          }
        ];
      }
    }

    return {
      chat_id: chat.id,
      mode_code: chat.mode_code,
      changed_at: changedAt
    };
  },

  async sendMessage(chatId, payload) {
    await wait(140);
    const chat = getChatById(chatId);

    const message: Message = {
      id: uid(),
      chat_id: chatId,
      ticket_id: payload.ticket_id,
      entity: 'operator',
      seq: ++state.globalSeq,
      text: payload.text,
      time: nowIso()
    };

    chat.messages = [...(chat.messages ?? []), message];
    chat.updated_at = message.time;

    const ticket = getTicketById(payload.ticket_id);
    if (ticket.status_code !== 'closed') {
      ticket.status_code = modeToTicketStatus(chat.mode_code, ticket.status_code);
    }

    return message;
  },

  async getSuggestions(_chatId, payload) {
    await wait(280);
    const base = payload.draft_context?.trim() || 'проверьте email и повторите запрос через 2 минуты';
    return {
      suggestions: toSuggestionText(base)
    };
  },

  async setDefaultNewTicketMode(mode_code) {
    await wait(130);
    state.defaultMode = mode_code;
    return {
      mode_code,
      updated_at: nowIso()
    };
  },

  async listRagDocuments(params) {
    await wait(160);
    const page = params?.page ?? 1;
    const pageSize = params?.page_size ?? 20;
    const includeDeleted = params?.include_deleted ?? false;

    const items = state.ragDocs
      .filter((item) => includeDeleted || !item.deleted_at)
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

    return paginate(items, page, pageSize);
  },

  async uploadRagDocument(payload) {
    await wait(420);

    const documentId = uid();
    const createdAt = nowIso();

    state.ragDocs.unshift({
      id: documentId,
      collection_id: uid(),
      source_type: payload.source_type,
      source_name: payload.source_name,
      current_version: 1,
      created_at: createdAt,
      deleted_at: null
    });

    return {
      document_id: documentId,
      ingestion_job_id: uid(),
      status: 'done'
    };
  },

  async deleteRagDocument(documentId) {
    await wait(120);
    const document = state.ragDocs.find((item) => item.id === documentId);
    if (!document) {
      throw new Error('Document not found');
    }

    const deletedAt = nowIso();
    document.deleted_at = deletedAt;

    return {
      document_id: document.id,
      deleted_at: deletedAt
    };
  }
};
