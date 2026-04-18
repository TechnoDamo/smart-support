'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Brain,
  ChevronLeft,
  ChevronRight,
  FileText,
  Loader2,
  MessageCircle,
  Moon,
  RefreshCcw,
  Search,
  Send,
  Settings,
  Sun,
  Trash2,
  Upload,
  Wifi,
  WifiOff
} from 'lucide-react';

import { supportApi, supportLabel } from '@/lib/api';
import { supportMockApi } from '@/lib/mock';
import {
  ApiError,
  type ApiMode,
  type Chat,
  type ChatDetails,
  type ChatModeCode,
  type Message,
  type RagDocument,
  type ServerStatus,
  type Suggestion,
  type ThemeMode,
  type Ticket,
  type TicketDetails,
  type TicketStatusCode
} from '@/lib/types';

type NavSection = 'inbox' | 'knowledge' | 'settings';
type InboxTab = 'new' | 'my' | 'closed';
type StatusFilter = TicketStatusCode | 'all';

type TicketRow = {
  ticket: Ticket;
  chat?: Chat;
  lastMessage?: Message;
  snippet: string;
  lastMessageAt: string;
};

type LocalTimelineEvent = {
  id: string;
  type: 'local';
  label: string;
  actor: 'operator' | 'ai_operator';
  created_at: string;
};

type TimelineItem =
  | {
      id: string;
      ts: string;
      kind: 'message';
      message: Message;
    }
  | {
      id: string;
      ts: string;
      kind: 'event';
      label: string;
      actor: string;
    };

const PAGE_SIZE = 20;
const POLL_MS = 4000;
const LOCAL_SETTINGS_KEY = 'smart-support-local-settings-v1';

function getId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function toHumanDate(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('ru-RU', {
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function formatTicketStatus(status: TicketStatusCode) {
  return supportLabel.status(status);
}

function actorLabel(actor: string) {
  if (actor === 'user') return 'Клиент';
  if (actor === 'operator') return 'Оператор';
  if (actor === 'ai_operator') return 'AI';
  return actor;
}

function messageSenderLabel(entity: Message['entity']) {
  if (entity === 'user') return 'Клиент';
  if (entity === 'ai_operator') return 'AI-оператор';
  return 'Оператор';
}

function parseFileExt(fileName: string) {
  const ext = fileName.split('.').pop();
  return ext ? ext.toUpperCase() : '—';
}

function ticketStatusByTab(tab: InboxTab): TicketStatusCode | undefined {
  if (tab === 'new') return 'pending_ai';
  if (tab === 'closed') return 'closed';
  return undefined;
}

function deriveUserDisplay(chat?: Chat) {
  if (!chat) return 'Неизвестный клиент';
  const suffix = chat.user_id.slice(0, 8);
  return `Клиент #${suffix}`;
}

function mapModeFromAction(target: 'handoff_human' | 'return_ai'): ChatModeCode {
  if (target === 'handoff_human') return 'no_ai';
  return 'ai_assist';
}

function translateMode(mode: ChatModeCode) {
  if (mode === 'full_ai') return 'AI ведёт диалог';
  if (mode === 'ai_assist') return 'AI помогает';
  return 'Без AI';
}

function translateEventLabel(label: string) {
  if (label.startsWith('ticket_status_changed:')) {
    return label
      .replace('ticket_status_changed:', 'Статус тикета:')
      .replace('pending_ai', 'ожидает AI')
      .replace('pending_human', 'ожидает человека')
      .replace('closed', 'закрыт')
      .replace('none', 'не задан');
  }

  if (label.startsWith('chat_mode_changed:')) {
    return label
      .replace('chat_mode_changed:', 'Режим чата:')
      .replace('full_ai', 'AI ведёт')
      .replace('ai_assist', 'AI помогает')
      .replace('no_ai', 'без AI')
      .replace('none', 'не задан');
  }

  if (label === 'ticket_renamed') return 'Тикет переименован';
  if (label === 'rag_sources_attached') return 'Подтянуты источники из базы знаний';
  if (label === 'ai_suggestions_generated') return 'Сгенерированы AI-подсказки';
  if (label === 'agent_message_sent') return 'Сообщение отправлено';
  if (label.startsWith('chat_mode_set:')) {
    return `Режим изменён: ${label
      .replace('chat_mode_set:', '')
      .trim()
      .replace('full_ai', 'AI ведёт диалог')
      .replace('ai_assist', 'AI помогает')
      .replace('no_ai', 'Без AI')}`;
  }

  return label;
}

function ThemeToggle({ theme, onChange }: { theme: ThemeMode; onChange: (value: ThemeMode) => void }) {
  return (
    <div className="soft-surface flex items-center gap-1 p-1">
      <button
        className={`btn ${theme === 'system' ? 'btn-primary' : 'btn-ghost'} px-2 py-1 text-xs`}
        onClick={() => onChange('system')}
      >
        Авто
      </button>
      <button
        className={`btn ${theme === 'light' ? 'btn-primary' : 'btn-ghost'} px-2 py-1`}
        onClick={() => onChange('light')}
        aria-label="Светлая тема"
      >
        <Sun size={14} />
      </button>
      <button
        className={`btn ${theme === 'dark' ? 'btn-primary' : 'btn-ghost'} px-2 py-1`}
        onClick={() => onChange('dark')}
        aria-label="Тёмная тема"
      >
        <Moon size={14} />
      </button>
    </div>
  );
}

export default function SupportWorkspacePage() {
  const [apiMode, setApiMode] = useState<ApiMode>('mock');
  const [serverStatus, setServerStatus] = useState<ServerStatus>('unknown');
  const [themeMode, setThemeMode] = useState<ThemeMode>('system');

  const [section, setSection] = useState<NavSection>('inbox');
  const [inboxTab, setInboxTab] = useState<InboxTab>('new');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [ticketPage, setTicketPage] = useState(1);

  const [isLoadingInbox, setIsLoadingInbox] = useState(false);
  const [inboxError, setInboxError] = useState<string | null>(null);

  const [rawRows, setRawRows] = useState<TicketRow[]>([]);
  const [ticketTotal, setTicketTotal] = useState(0);
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);

  const [ticketDetails, setTicketDetails] = useState<TicketDetails | null>(null);
  const [chatDetails, setChatDetails] = useState<ChatDetails | null>(null);
  const [isLoadingTicketCard, setIsLoadingTicketCard] = useState(false);

  const [composerText, setComposerText] = useState('');
  const [isSendingMessage, setIsSendingMessage] = useState(false);

  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [isLoadingSuggestions, setIsLoadingSuggestions] = useState(false);
  const [expandedSourcesSuggestionId, setExpandedSourcesSuggestionId] = useState<string | null>(null);

  const [localEventsByTicket, setLocalEventsByTicket] = useState<Record<string, LocalTimelineEvent[]>>({});
  const [docNameById, setDocNameById] = useState<Record<string, string>>({});

  const [ticketCounters, setTicketCounters] = useState({ pending_ai: 0, pending_human: 0, closed: 0 });

  const [kbPage, setKbPage] = useState(1);
  const [kbIncludeDeleted, setKbIncludeDeleted] = useState(false);
  const [kbDocs, setKbDocs] = useState<RagDocument[]>([]);
  const [kbTotal, setKbTotal] = useState(0);
  const [kbError, setKbError] = useState<string | null>(null);
  const [isKbLoading, setIsKbLoading] = useState(false);
  const [isKbUploading, setIsKbUploading] = useState(false);
  const [ingestionStatusMap, setIngestionStatusMap] = useState<Record<string, string>>({});

  const [defaultModeSetting, setDefaultModeSetting] = useState<ChatModeCode>('ai_assist');
  const [settingsSaveState, setSettingsSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [autoCloseMinutes, setAutoCloseMinutes] = useState(30);
  const [autoSummaryAfterClose, setAutoSummaryAfterClose] = useState(true);
  const [pushSummaryToRag, setPushSummaryToRag] = useState(false);

  const [isAutoScroll, setIsAutoScroll] = useState(true);
  const timelineRef = useRef<HTMLDivElement | null>(null);

  const api = useMemo(() => (apiMode === 'mock' ? supportMockApi : supportApi), [apiMode]);

  const openInboxCount = ticketCounters.pending_ai + ticketCounters.pending_human;

  const selectedRow = useMemo(() => {
    if (!selectedTicketId) return null;
    return rawRows.find((row) => row.ticket.id === selectedTicketId) ?? null;
  }, [rawRows, selectedTicketId]);

  const filteredRows = useMemo(() => {
    let rows = [...rawRows];

    if (inboxTab === 'my') {
      rows = rows.filter((row) => row.ticket.status_code !== 'closed');
    }
    if (inboxTab === 'new') {
      rows = rows.filter((row) => row.ticket.status_code === 'pending_ai');
    }
    if (inboxTab === 'closed') {
      rows = rows.filter((row) => row.ticket.status_code === 'closed');
    }

    if (statusFilter !== 'all') {
      rows = rows.filter((row) => row.ticket.status_code === statusFilter);
    }

    const normalizedSearch = search.trim().toLowerCase();
    if (normalizedSearch) {
      rows = rows.filter((row) => {
        const haystack = [
          row.ticket.id,
          row.ticket.title,
          row.ticket.summary,
          row.lastMessage?.text,
          row.ticket.status_code,
          row.chat?.channel.code,
          row.chat?.channel.name
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();

        return haystack.includes(normalizedSearch);
      });
    }

    rows.sort((a, b) => new Date(b.lastMessageAt).getTime() - new Date(a.lastMessageAt).getTime());
    return rows;
  }, [rawRows, inboxTab, statusFilter, search]);

  const timelineItems = useMemo<TimelineItem[]>(() => {
    if (!selectedTicketId) return [];

    const messages = (chatDetails?.messages ?? []).filter((item) => item.ticket_id === selectedTicketId);
    const statusEvents = ticketDetails?.status_events ?? [];
    const modeEvents = chatDetails?.mode_events ?? [];
    const localEvents = localEventsByTicket[selectedTicketId] ?? [];

    const all: TimelineItem[] = [];

    for (const message of messages) {
      all.push({
        id: `msg-${message.id}`,
        kind: 'message',
        ts: message.time,
        message
      });
    }

    for (const event of statusEvents) {
      const from = event.from_status_code ?? 'none';
      all.push({
        id: `st-${event.created_at}-${event.to_status_code}`,
        kind: 'event',
        ts: event.created_at,
        actor: actorLabel(event.changed_by),
        label: `ticket_status_changed: ${from} -> ${event.to_status_code}`
      });
    }

    for (const event of modeEvents) {
      const from = event.from_mode_code ?? 'none';
      all.push({
        id: `md-${event.created_at}-${event.to_mode_code}`,
        kind: 'event',
        ts: event.created_at,
        actor: actorLabel(event.changed_by),
        label: `chat_mode_changed: ${from} -> ${event.to_mode_code}`
      });
    }

    for (const event of localEvents) {
      all.push({
        id: event.id,
        kind: 'event',
        ts: event.created_at,
        actor: actorLabel(event.actor),
        label: event.label
      });
    }

    all.sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());
    return all;
  }, [chatDetails?.messages, chatDetails?.mode_events, ticketDetails?.status_events, selectedTicketId, localEventsByTicket]);

  const kbCounters = useMemo(() => {
    const values = Object.values(ingestionStatusMap);
    return {
      queued: values.filter((value) => value === 'queued').length,
      processing: values.filter((value) => value === 'processing').length,
      done: values.filter((value) => value === 'done').length,
      failed: values.filter((value) => value === 'failed').length
    };
  }, [ingestionStatusMap]);

  const addLocalEvent = useCallback(
    (ticketId: string, label: string, actor: 'operator' | 'ai_operator' = 'operator') => {
      const event: LocalTimelineEvent = {
        id: getId(),
        type: 'local',
        label,
        actor,
        created_at: new Date().toISOString()
      };

      setLocalEventsByTicket((prev) => ({
        ...prev,
        [ticketId]: [...(prev[ticketId] ?? []), event]
      }));
    },
    []
  );

  const ensureDocNames = useCallback(async () => {
    try {
      const response = await api.listRagDocuments({ page: 1, page_size: 200, include_deleted: true });
      const nextMap: Record<string, string> = {};
      for (const doc of response.items) {
        nextMap[doc.id] = doc.source_name;
      }
      setDocNameById(nextMap);
    } catch {
      // ignore
    }
  }, [api]);

  const loadInbox = useCallback(
    async (silent = false) => {
      if (!silent) {
        setIsLoadingInbox(true);
      }
      setInboxError(null);

      try {
        const statusFromTab = ticketStatusByTab(inboxTab);
        const queryStatus = statusFilter === 'all' ? statusFromTab : statusFilter;

        const basePromises: Array<Promise<unknown>> = [
          api.listTickets({ page: ticketPage, page_size: PAGE_SIZE, status: queryStatus }),
          api.listChats({ page: 1, page_size: 200 })
        ];

        if (!silent) {
          basePromises.push(
            api.listTickets({ page: 1, page_size: 1, status: 'pending_ai' }),
            api.listTickets({ page: 1, page_size: 1, status: 'pending_human' }),
            api.listTickets({ page: 1, page_size: 1, status: 'closed' })
          );
        }

        const responses = await Promise.all(basePromises);
        const ticketsResponse = responses[0] as Awaited<ReturnType<typeof api.listTickets>>;
        const chatsResponse = responses[1] as Awaited<ReturnType<typeof api.listChats>>;

        if (!silent) {
          const aiTotal = (responses[2] as Awaited<ReturnType<typeof api.listTickets>>).total;
          const humanTotal = (responses[3] as Awaited<ReturnType<typeof api.listTickets>>).total;
          const closedTotal = (responses[4] as Awaited<ReturnType<typeof api.listTickets>>).total;

          setTicketCounters({
            pending_ai: aiTotal,
            pending_human: humanTotal,
            closed: closedTotal
          });
        }

        const chatMap = chatsResponse.items.reduce<Record<string, Chat>>((acc, chat) => {
          acc[chat.id] = chat;
          return acc;
        }, {});

        const uniqueChatIds = Array.from(new Set(ticketsResponse.items.map((item) => item.chat_id)));

        const chatDetailSettled = await Promise.allSettled(uniqueChatIds.map((chatId) => api.getChat(chatId)));

        const chatDetailsMap: Record<string, ChatDetails> = {};
        for (const result of chatDetailSettled) {
          if (result.status === 'fulfilled') {
            chatDetailsMap[result.value.id] = result.value;
          }
        }

        const rows: TicketRow[] = ticketsResponse.items.map((ticket) => {
          const chat = chatMap[ticket.chat_id];
          const chatDetails = chatDetailsMap[ticket.chat_id];
          const ticketMessages = (chatDetails?.messages ?? []).filter((message) => message.ticket_id === ticket.id);
          const lastMessage = ticketMessages[ticketMessages.length - 1];
          const lastMessageAt =
            lastMessage?.time ?? chatDetails?.updated_at ?? ticket.time_closed ?? ticket.time_started;

          return {
            ticket,
            chat,
            lastMessage,
            lastMessageAt,
            snippet: lastMessage?.text ?? ticket.summary ?? ticket.title ?? 'Без сообщений'
          };
        });

        rows.sort((a, b) => new Date(b.lastMessageAt).getTime() - new Date(a.lastMessageAt).getTime());

        setRawRows(rows);
        setTicketTotal(ticketsResponse.total);

        if (rows.length > 0) {
          setSelectedTicketId((current) => {
            if (!current) return rows[0].ticket.id;
            const exists = rows.some((row) => row.ticket.id === current);
            return exists ? current : rows[0].ticket.id;
          });
        } else {
          setSelectedTicketId(null);
        }

        if (apiMode === 'live') {
          setServerStatus('online');
        }
      } catch (error) {
        if (error instanceof ApiError) {
          setInboxError(error.message);
        } else {
          setInboxError('Не удалось загрузить список диалогов');
        }

        if (apiMode === 'live') {
          setServerStatus('offline');
        }
      } finally {
        if (!silent) {
          setIsLoadingInbox(false);
        }
      }
    },
    [api, apiMode, inboxTab, statusFilter, ticketPage]
  );

  const loadTicketCard = useCallback(
    async (ticketId: string, silent = false) => {
      const row = rawRows.find((item) => item.ticket.id === ticketId);
      if (!row) {
        setTicketDetails(null);
        setChatDetails(null);
        return;
      }

      if (!silent) {
        setIsLoadingTicketCard(true);
      }

      try {
        const [ticketResponse, chatResponse] = await Promise.all([
          api.getTicket(ticketId),
          api.getChat(row.ticket.chat_id)
        ]);

        setTicketDetails(ticketResponse);
        setChatDetails(chatResponse);

        if (apiMode === 'live') {
          setServerStatus('online');
        }
      } catch (error) {
        if (!silent) {
          setInboxError(error instanceof Error ? error.message : 'Не удалось открыть диалог');
        }

        if (apiMode === 'live') {
          setServerStatus('offline');
        }
      } finally {
        if (!silent) {
          setIsLoadingTicketCard(false);
        }
      }
    },
    [api, apiMode, rawRows]
  );

  const loadKnowledgeBase = useCallback(
    async (silent = false) => {
      if (!silent) {
        setIsKbLoading(true);
      }
      setKbError(null);

      try {
        const response = await api.listRagDocuments({
          page: kbPage,
          page_size: PAGE_SIZE,
          include_deleted: kbIncludeDeleted
        });

        setKbDocs(response.items);
        setKbTotal(response.total);

        const names = response.items.reduce<Record<string, string>>((acc, doc) => {
          acc[doc.id] = doc.source_name;
          return acc;
        }, {});

        setDocNameById((prev) => ({ ...prev, ...names }));
      } catch (error) {
        setKbError(error instanceof Error ? error.message : 'Не удалось загрузить документы');
      } finally {
        if (!silent) {
          setIsKbLoading(false);
        }
      }
    },
    [api, kbPage, kbIncludeDeleted]
  );

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const params = new URLSearchParams(window.location.search);
    const sectionParam = params.get('section');
    const tabParam = params.get('tab');
    const statusParam = params.get('status');
    const pageParam = params.get('page');
    const qParam = params.get('q');

    if (sectionParam === 'inbox' || sectionParam === 'knowledge' || sectionParam === 'settings') {
      setSection(sectionParam);
    }
    if (tabParam === 'new' || tabParam === 'my' || tabParam === 'closed') {
      setInboxTab(tabParam);
    }
    if (
      statusParam === 'all' ||
      statusParam === 'pending_ai' ||
      statusParam === 'pending_human' ||
      statusParam === 'closed'
    ) {
      setStatusFilter(statusParam);
    }
    if (pageParam) {
      const parsed = Number(pageParam);
      if (Number.isFinite(parsed) && parsed >= 1) {
        setTicketPage(parsed);
      }
    }
    if (qParam) {
      setSearch(qParam);
    }
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const params = new URLSearchParams();
    params.set('section', section);

    if (section === 'inbox') {
      params.set('tab', inboxTab);
      params.set('status', statusFilter);
      params.set('page', String(ticketPage));
      if (search.trim()) {
        params.set('q', search.trim());
      }
    }

    const nextUrl = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState({}, '', nextUrl);
  }, [section, inboxTab, statusFilter, ticketPage, search]);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const raw = window.localStorage.getItem(LOCAL_SETTINGS_KEY);
    if (!raw) return;

    try {
      const parsed = JSON.parse(raw) as {
        themeMode?: ThemeMode;
        autoCloseMinutes?: number;
        autoSummaryAfterClose?: boolean;
        pushSummaryToRag?: boolean;
      };

      if (parsed.themeMode) {
        setThemeMode(parsed.themeMode);
      }
      if (typeof parsed.autoCloseMinutes === 'number') {
        setAutoCloseMinutes(parsed.autoCloseMinutes);
      }
      if (typeof parsed.autoSummaryAfterClose === 'boolean') {
        setAutoSummaryAfterClose(parsed.autoSummaryAfterClose);
      }
      if (typeof parsed.pushSummaryToRag === 'boolean') {
        setPushSummaryToRag(parsed.pushSummaryToRag);
      }
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    window.localStorage.setItem(
      LOCAL_SETTINGS_KEY,
      JSON.stringify({
        themeMode,
        autoCloseMinutes,
        autoSummaryAfterClose,
        pushSummaryToRag
      })
    );
  }, [themeMode, autoCloseMinutes, autoSummaryAfterClose, pushSummaryToRag]);

  useEffect(() => {
    const root = document.documentElement;

    const apply = (isDark: boolean) => {
      root.classList.toggle('dark', isDark);
    };

    if (themeMode === 'dark') {
      apply(true);
      return;
    }

    if (themeMode === 'light') {
      apply(false);
      return;
    }

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    apply(mediaQuery.matches);

    const onChange = (event: MediaQueryListEvent) => {
      apply(event.matches);
    };

    mediaQuery.addEventListener('change', onChange);
    return () => mediaQuery.removeEventListener('change', onChange);
  }, [themeMode]);

  useEffect(() => {
    if (apiMode === 'mock') {
      setServerStatus('online');
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        await supportApi.ping();
        if (!cancelled) {
          setServerStatus('online');
        }
      } catch {
        if (!cancelled) {
          setServerStatus('offline');
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [apiMode]);

  useEffect(() => {
    loadInbox();
    ensureDocNames();
  }, [loadInbox, ensureDocNames]);

  useEffect(() => {
    if (!selectedTicketId || section !== 'inbox') return;
    loadTicketCard(selectedTicketId);
  }, [selectedTicketId, loadTicketCard, section]);

  useEffect(() => {
    if (section !== 'inbox') return;

    const timer = window.setInterval(() => {
      loadInbox(true);
      if (selectedTicketId) {
        loadTicketCard(selectedTicketId, true);
      }
    }, POLL_MS);

    return () => window.clearInterval(timer);
  }, [loadInbox, loadTicketCard, selectedTicketId, section]);

  useEffect(() => {
    if (section !== 'knowledge') return;
    loadKnowledgeBase();
  }, [section, loadKnowledgeBase]);

  useEffect(() => {
    if (filteredRows.length === 0) {
      setSelectedTicketId(null);
      return;
    }

    if (!selectedTicketId || !filteredRows.some((item) => item.ticket.id === selectedTicketId)) {
      setSelectedTicketId(filteredRows[0].ticket.id);
    }
  }, [filteredRows, selectedTicketId]);

  useEffect(() => {
    if (!timelineRef.current || !isAutoScroll) return;
    timelineRef.current.scrollTo({
      top: timelineRef.current.scrollHeight,
      behavior: 'smooth'
    });
  }, [timelineItems, isAutoScroll]);

  const onTimelineScroll = useCallback(() => {
    const el = timelineRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 44;
    setIsAutoScroll(nearBottom);
  }, []);

  const onManualRefresh = useCallback(async () => {
    await Promise.all([loadInbox(false), selectedTicketId ? loadTicketCard(selectedTicketId, false) : Promise.resolve()]);
  }, [loadInbox, loadTicketCard, selectedTicketId]);

  const onChangeChatMode = useCallback(
    async (nextMode: ChatModeCode, reason: string) => {
      if (!selectedRow) return;

      try {
        await api.changeChatMode(selectedRow.ticket.chat_id, {
          to_mode_code: nextMode,
          reason
        });

        addLocalEvent(selectedRow.ticket.id, `chat_mode_set: ${nextMode}`);
        await loadInbox(true);
        await loadTicketCard(selectedRow.ticket.id, true);
      } catch (error) {
        setInboxError(error instanceof Error ? error.message : 'Не удалось сменить режим чата');
      }
    },
    [addLocalEvent, api, loadInbox, loadTicketCard, selectedRow]
  );

  const onQuickAction = useCallback(
    async (action: 'handoff_human' | 'return_ai') => {
      if (!selectedRow) return;
      const mode = mapModeFromAction(action);
      const reason = action === 'handoff_human' ? 'handoff_to_human' : 'return_to_ai_helper';
      await onChangeChatMode(mode, reason);
    },
    [onChangeChatMode, selectedRow]
  );

  const onGenerateSuggestions = useCallback(async () => {
    if (!selectedRow) return;

    try {
      setIsLoadingSuggestions(true);
      const response = await api.getSuggestions(selectedRow.ticket.chat_id, {
        ticket_id: selectedRow.ticket.id,
        draft_context: composerText.trim() || undefined,
        max_suggestions: 5
      });

      setSuggestions(response.suggestions);
      setExpandedSourcesSuggestionId(null);
      const hasAnySources = response.suggestions.some((suggestion) => (suggestion.citations?.length ?? 0) > 0);

      addLocalEvent(
        selectedRow.ticket.id,
        hasAnySources ? 'rag_sources_attached' : 'ai_suggestions_generated',
        'ai_operator'
      );
    } catch (error) {
      setInboxError(error instanceof Error ? error.message : 'Не удалось получить AI-подсказки');
    } finally {
      setIsLoadingSuggestions(false);
    }
  }, [addLocalEvent, api, composerText, selectedRow]);

  const onUseSuggestion = useCallback((text: string) => {
    setComposerText((prev) => {
      if (!prev.trim()) return text.trim();
      return `${prev.trim()}\n\n${text.trim()}`;
    });
  }, []);

  const onToggleSuggestionSources = useCallback((suggestionId: string) => {
    setExpandedSourcesSuggestionId((current) => (current === suggestionId ? null : suggestionId));
  }, []);

  const onSendMessage = useCallback(async () => {
    if (!selectedRow || !composerText.trim()) return;

    try {
      setIsSendingMessage(true);

      await api.sendMessage(selectedRow.ticket.chat_id, {
        ticket_id: selectedRow.ticket.id,
        text: composerText.trim()
      });

      setComposerText('');
      addLocalEvent(selectedRow.ticket.id, 'agent_message_sent');

      await loadTicketCard(selectedRow.ticket.id, true);
      await loadInbox(true);
    } catch (error) {
      setInboxError(error instanceof Error ? error.message : 'Не удалось отправить сообщение');
    } finally {
      setIsSendingMessage(false);
    }
  }, [addLocalEvent, api, composerText, loadInbox, loadTicketCard, selectedRow]);

  const onUploadKbFiles = useCallback(
    async (fileList: FileList | null) => {
      if (!fileList || fileList.length === 0) return;

      const files = Array.from(fileList);

      try {
        setIsKbUploading(true);

        for (const file of files) {
          const response = await api.uploadRagDocument({
            source_type: 'telegram_upload',
            source_name: file.name,
            file
          });

          setIngestionStatusMap((prev) => ({
            ...prev,
            [response.document_id]: response.status
          }));
        }

        await loadKnowledgeBase(true);
      } catch (error) {
        setKbError(error instanceof Error ? error.message : 'Не удалось загрузить документы');
      } finally {
        setIsKbUploading(false);
      }
    },
    [api, loadKnowledgeBase]
  );

  const onDeleteKbDocument = useCallback(
    async (documentId: string) => {
      try {
        await api.deleteRagDocument(documentId);
        await loadKnowledgeBase(true);
      } catch (error) {
        setKbError(error instanceof Error ? error.message : 'Не удалось удалить документ');
      }
    },
    [api, loadKnowledgeBase]
  );

  const onSaveDefaultMode = useCallback(async () => {
    try {
      setSettingsSaveState('saving');
      await api.setDefaultNewTicketMode(defaultModeSetting);
      setSettingsSaveState('saved');
      window.setTimeout(() => setSettingsSaveState('idle'), 1500);
    } catch {
      setSettingsSaveState('error');
    }
  }, [api, defaultModeSetting]);

  return (
    <main className="mx-auto max-w-[1680px] px-3 pb-4 pt-4 sm:px-4 sm:pt-5 lg:px-6">
      <header className="surface fade-in-up mb-3 p-3 sm:p-4">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex min-w-0 flex-col gap-3">
            <div>
              <div className="text-xs font-medium uppercase tracking-[0.08em] text-[var(--muted)]">
                Smart Support
              </div>
              <div className="mt-1 text-xl font-semibold">Рабочее место оператора</div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                className={`btn px-3 py-2 text-sm ${section === 'inbox' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setSection('inbox')}
              >
                <MessageCircle size={14} />
                Диалоги
                <span className="badge badge-muted ml-1">{openInboxCount}</span>
              </button>

              <button
                className={`btn px-3 py-2 text-sm ${section === 'knowledge' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setSection('knowledge')}
              >
                <FileText size={14} />
                База знаний
              </button>

              <button
                className={`btn px-3 py-2 text-sm ${section === 'settings' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setSection('settings')}
              >
                <Settings size={14} />
                Настройки
              </button>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="soft-surface flex items-center gap-1 p-1 text-sm">
              <button
                className={`btn px-3 py-1.5 text-sm ${apiMode === 'mock' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setApiMode('mock')}
              >
                Тестовый режим
              </button>
              <button
                className={`btn px-3 py-1.5 text-sm ${apiMode === 'live' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setApiMode('live')}
              >
                Реальный API
              </button>
            </div>

            <div className="soft-surface flex items-center gap-2 px-3 py-2 text-sm text-[var(--muted)]">
              {serverStatus === 'online' ? <Wifi size={14} /> : <WifiOff size={14} />}
              {serverStatus === 'online'
                ? 'API подключён'
                : serverStatus === 'offline'
                  ? 'API недоступен'
                  : 'Статус API'}
            </div>

            <ThemeToggle theme={themeMode} onChange={setThemeMode} />
          </div>
        </div>
      </header>

      {inboxError ? (
        <div className="mb-3 rounded-xl bg-[rgba(209,70,70,0.13)] px-3 py-2 text-sm text-[var(--danger)]">
          {inboxError}
        </div>
      ) : null}

      {section === 'inbox' ? (
        <div className="grid h-[calc(100dvh-190px)] min-h-[560px] gap-3 xl:grid-cols-[320px_minmax(0,1fr)]">
          <section className="surface fade-in-up flex min-h-0 flex-col p-3">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              {(['new', 'my', 'closed'] as const).map((tab) => (
                <button
                  key={tab}
                  className={`btn px-3 py-1.5 text-sm ${inboxTab === tab ? 'btn-primary' : 'btn-ghost'}`}
                  onClick={() => {
                    setInboxTab(tab);
                    setTicketPage(1);
                  }}
                >
                  {tab === 'new' ? 'Новые' : tab === 'my' ? 'Активные' : 'Закрытые'}
                </button>
              ))}
            </div>

            <div className="mb-3 grid grid-cols-1 gap-2">
              <label className="relative">
                <Search
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted)]"
                  size={14}
                />
                <input
                  className="field pl-8"
                  placeholder="Поиск по диалогам"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </label>

              <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_auto]">
                <select
                  className="field"
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
                >
                  <option value="all">Все статусы</option>
                  <option value="pending_ai">Ожидают AI</option>
                  <option value="pending_human">Ожидают человека</option>
                  <option value="closed">Закрытые</option>
                </select>

                <button className="btn justify-center" onClick={onManualRefresh} aria-label="Обновить">
                  <RefreshCcw size={14} />
                </button>
              </div>
            </div>

            <div className="mb-2 flex items-center justify-between text-xs text-[var(--muted)]">
              <div>
                Диалоги: {filteredRows.length} из {ticketTotal}
              </div>
              {isLoadingInbox ? (
                <div className="inline-flex items-center gap-1">
                  <Loader2 size={13} className="animate-spin" />
                  Обновляем...
                </div>
              ) : null}
            </div>

            <div className="scrollbar-thin flex-1 space-y-2 overflow-y-auto pr-1">
              {filteredRows.map((row) => {
                const isActive = selectedTicketId === row.ticket.id;
                const isClosed = row.ticket.status_code === 'closed';
                const aiAutoReply = row.chat?.mode_code === 'full_ai' && !isClosed;

                return (
                  <button
                    key={row.ticket.id}
                    className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                      isActive
                        ? 'border-[var(--accent)] bg-[var(--accent-soft)]'
                        : 'border-[var(--line)] bg-[var(--panel-solid)] hover:bg-[var(--bg-soft)]'
                    } ${row.ticket.status_code === 'pending_ai' ? 'status-pulse' : ''}`}
                    onClick={() => setSelectedTicketId(row.ticket.id)}
                  >
                    <div className="mb-2 flex items-start justify-between gap-2">
                      <div className="truncate text-sm font-semibold">{deriveUserDisplay(row.chat)}</div>
                      {aiAutoReply ? <span className="ai-dot" title="AI отвечает автоматически" /> : null}
                    </div>

                    <div className="line-clamp-2 text-sm text-[var(--muted)]">{row.snippet}</div>

                    <div className="mt-3 flex flex-wrap items-center gap-1">
                      <span
                        className={`badge ${
                          row.ticket.status_code === 'closed'
                            ? 'badge-danger'
                            : row.ticket.status_code === 'pending_human'
                              ? 'badge-success'
                              : 'badge-accent'
                        }`}
                      >
                        {formatTicketStatus(row.ticket.status_code)}
                      </span>
                      <span className="badge badge-muted">{toHumanDate(row.lastMessageAt)}</span>
                    </div>
                  </button>
                );
              })}

              {filteredRows.length === 0 ? (
                <div className="rounded-xl bg-[var(--bg-soft)] p-4 text-sm text-[var(--muted)]">
                  Ничего не найдено.
                </div>
              ) : null}
            </div>

            <div className="mt-3 flex items-center justify-between gap-2">
              <button
                className="btn inline-flex items-center gap-1 text-sm"
                disabled={ticketPage <= 1}
                onClick={() => setTicketPage((prev) => Math.max(1, prev - 1))}
              >
                <ChevronLeft size={14} />
                Назад
              </button>

              <div className="text-xs text-[var(--muted)]">Страница {ticketPage}</div>

              <button
                className="btn inline-flex items-center gap-1 text-sm"
                disabled={ticketPage * PAGE_SIZE >= ticketTotal}
                onClick={() => setTicketPage((prev) => prev + 1)}
              >
                Вперёд
                <ChevronRight size={14} />
              </button>
            </div>
          </section>

          <section className="surface fade-in-up min-h-0 overflow-hidden p-3">
            {!selectedRow ? (
              <div className="flex h-full items-center justify-center text-sm text-[var(--muted)]">
                Выберите диалог слева
              </div>
            ) : (
              <div className="flex h-full min-h-0 flex-col">
                <div className="mb-3 rounded-2xl bg-[var(--panel-solid)] p-3">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="text-base font-semibold">
                          {ticketDetails?.title ?? selectedRow.ticket.title ?? 'Без названия'}
                        </div>
                        <span
                          className={`badge ${
                            selectedRow.ticket.status_code === 'closed'
                              ? 'badge-danger'
                              : selectedRow.ticket.status_code === 'pending_human'
                                ? 'badge-success'
                                : 'badge-accent'
                          }`}
                        >
                          {formatTicketStatus(selectedRow.ticket.status_code)}
                        </span>
                        <span className="badge badge-muted">
                          {translateMode((chatDetails ?? selectedRow.chat)?.mode_code ?? 'ai_assist')}
                        </span>
                      </div>
                      <div className="mt-1 text-sm text-[var(--muted)]">{deriveUserDisplay(chatDetails ?? selectedRow.chat)}</div>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <select
                        className="field min-w-[180px]"
                        value={(chatDetails ?? selectedRow.chat)?.mode_code ?? 'ai_assist'}
                        onChange={(event) => onChangeChatMode(event.target.value as ChatModeCode, 'mode_selected')}
                      >
                        <option value="full_ai">AI ведёт диалог</option>
                        <option value="ai_assist">AI помогает оператору</option>
                        <option value="no_ai">Без AI</option>
                      </select>
                      <button
                        className="btn"
                        onClick={() => onQuickAction('handoff_human')}
                        disabled={selectedRow.ticket.status_code === 'closed'}
                      >
                        Передать человеку
                      </button>
                      <button className="btn" onClick={() => onQuickAction('return_ai')}>
                        Вернуть AI
                      </button>
                    </div>
                  </div>
                </div>

                <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl bg-[var(--bg-soft)]">
                  <div className="flex items-center justify-between border-b border-[var(--line)] px-4 py-3">
                    <div className="text-sm font-semibold">Переписка</div>
                    {isLoadingTicketCard ? (
                      <div className="inline-flex items-center gap-1 text-xs text-[var(--muted)]">
                        <Loader2 size={13} className="animate-spin" />
                        Загрузка...
                      </div>
                    ) : null}
                  </div>

                  <div
                    ref={timelineRef}
                    onScroll={onTimelineScroll}
                    className="scrollbar-thin flex-1 overflow-y-auto px-3 py-4"
                  >
                    <div className="mx-auto flex max-w-[860px] flex-col gap-3">
                      {timelineItems.map((item) => {
                        if (item.kind === 'message') {
                          const sender = messageSenderLabel(item.message.entity);
                          const isClient = item.message.entity === 'user';
                          const isAi = item.message.entity === 'ai_operator';

                          return (
                            <div key={item.id} className={`flex ${isClient ? 'justify-start' : 'justify-end'}`}>
                              <div
                                className={`max-w-[78%] rounded-2xl px-4 py-3 shadow-sm ${
                                  isClient
                                    ? 'bg-[var(--panel-solid)] text-[var(--text)]'
                                    : isAi
                                      ? 'bg-[rgba(47,125,244,0.14)] text-[var(--text)]'
                                      : 'bg-[rgba(15,159,101,0.14)] text-[var(--text)]'
                                }`}
                              >
                                <div className="mb-1 flex items-center justify-between gap-3 text-[11px] text-[var(--muted)]">
                                  <span className="font-medium">{sender}</span>
                                  <span>{toHumanDate(item.ts)}</span>
                                </div>
                                <div className="whitespace-pre-wrap text-sm leading-6">{item.message.text}</div>
                              </div>
                            </div>
                          );
                        }

                        return (
                          <div key={item.id} className="flex justify-center">
                            <div className="max-w-[80%] rounded-full bg-[var(--panel-solid)] px-3 py-1.5 text-center text-xs text-[var(--muted)]">
                              {translateEventLabel(item.label)} • {item.actor} • {toHumanDate(item.ts)}
                            </div>
                          </div>
                        );
                      })}

                      {timelineItems.length === 0 ? (
                        <div className="rounded-2xl bg-[var(--panel-solid)] p-4 text-sm text-[var(--muted)]">
                          Сообщений пока нет.
                        </div>
                      ) : null}
                    </div>
                  </div>

                  <div className="sticky bottom-0 z-10 border-t border-[var(--line)] bg-[var(--panel-solid)] p-3">
                    <div className="mx-auto max-w-[860px]">
                      <textarea
                        className="field min-h-[98px] resize-y"
                        placeholder="Введите сообщение клиенту"
                        value={composerText}
                        onChange={(event) => setComposerText(event.target.value)}
                      />

                      <div className="mt-3 flex flex-wrap gap-2">
                        <button className="btn" onClick={onGenerateSuggestions} disabled={isLoadingSuggestions}>
                          <Brain size={14} />
                          {isLoadingSuggestions ? 'Генерируем...' : 'Подсказки'}
                        </button>
                        <button
                          className="btn btn-primary inline-flex items-center gap-1"
                          onClick={onSendMessage}
                          disabled={isSendingMessage || !composerText.trim()}
                        >
                          {isSendingMessage ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                          Отправить
                        </button>
                      </div>

                      <div className="mt-3 space-y-2">
                        {!isLoadingSuggestions && suggestions.length === 0 ? (
                          <div className="rounded-xl bg-[var(--bg-soft)] px-3 py-2 text-xs text-[var(--muted)]">
                            Подсказки появятся после нажатия кнопки «Подсказки».
                          </div>
                        ) : null}

                        {suggestions.map((suggestion, index) => (
                          <div key={suggestion.id} className="rounded-xl bg-[var(--bg-soft)] p-2">
                            <div className="flex flex-wrap items-center gap-2">
                              <button
                                className="btn text-left text-xs"
                                onClick={() => onUseSuggestion(suggestion.text)}
                              >
                                Вариант {index + 1}
                              </button>
                              <button
                                className="btn text-xs"
                                onClick={() => onToggleSuggestionSources(suggestion.id)}
                              >
                                {expandedSourcesSuggestionId === suggestion.id ? 'Скрыть источники' : 'Откуда этот источник'}
                              </button>
                            </div>

                            <div className="mt-2 line-clamp-2 whitespace-pre-wrap text-xs text-[var(--muted)]">
                              {suggestion.text}
                            </div>

                            {expandedSourcesSuggestionId === suggestion.id ? (
                              <div className="mt-2 space-y-2">
                                {(suggestion.citations ?? []).map((citation) => (
                                  <div key={`${suggestion.id}-${citation.chunk_id}`} className="rounded-lg bg-[var(--panel-solid)] p-2 text-xs">
                                    <div>Документ: {docNameById[citation.document_id] ?? citation.document_id}</div>
                                    <div>Фрагмент: {citation.chunk_id}</div>
                                    <div>Оценка: {citation.score.toFixed(3)}</div>
                                  </div>
                                ))}
                                {(suggestion.citations ?? []).length === 0 ? (
                                  <div className="rounded-lg bg-[var(--panel-solid)] p-2 text-xs text-[var(--muted)]">
                                    Для этого варианта источники не найдены.
                                  </div>
                                ) : null}
                              </div>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </section>
        </div>
      ) : null}

      {section === 'knowledge' ? (
        <section className="surface fade-in-up min-h-[540px] p-3">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-sm font-semibold">База знаний</div>
              <div className="text-xs text-[var(--muted)]">Документы для RAG</div>
            </div>

            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="badge badge-muted">в очереди: {kbCounters.queued}</span>
              <span className="badge badge-muted">обработка: {kbCounters.processing}</span>
              <span className="badge badge-success">готово: {kbCounters.done}</span>
              <span className="badge badge-danger">ошибка: {kbCounters.failed}</span>
            </div>
          </div>

          <div className="mb-3 grid gap-2 sm:grid-cols-[1fr_auto_auto] sm:items-center">
            <label
              className="soft-surface flex cursor-pointer items-center justify-center gap-2 px-4 py-5 text-sm text-[var(--muted)]"
              onDragOver={(event) => {
                event.preventDefault();
                event.dataTransfer.dropEffect = 'copy';
              }}
              onDrop={(event) => {
                event.preventDefault();
                void onUploadKbFiles(event.dataTransfer.files);
              }}
            >
              <Upload size={14} />
              Перетащите файлы или нажмите для выбора
              <input
                type="file"
                className="hidden"
                multiple
                accept=".pdf,.docx,.txt,.md,.csv"
                onChange={(event) => onUploadKbFiles(event.target.files)}
              />
            </label>

            <label className="btn inline-flex items-center gap-2">
              <input
                type="checkbox"
                checked={kbIncludeDeleted}
                onChange={(event) => setKbIncludeDeleted(event.target.checked)}
              />
              Показывать удалённые
            </label>

            <button className="btn" onClick={() => loadKnowledgeBase(false)}>
              <RefreshCcw size={14} />
            </button>
          </div>

          {kbError ? (
            <div className="mb-2 rounded-xl bg-[rgba(209,70,70,0.13)] px-3 py-2 text-sm text-[var(--danger)]">
              {kbError}
            </div>
          ) : null}

          {isKbUploading ? (
            <div className="mb-2 inline-flex items-center gap-2 text-sm text-[var(--muted)]">
              <Loader2 size={14} className="animate-spin" />
              Идёт загрузка...
            </div>
          ) : null}

          <div className="scrollbar-thin overflow-auto rounded-xl bg-[var(--panel-solid)]">
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs text-[var(--muted)]">
                <tr>
                  <th className="px-3 py-2">Файл</th>
                  <th className="px-3 py-2">Тип</th>
                  <th className="px-3 py-2">Источник</th>
                  <th className="px-3 py-2">Версия</th>
                  <th className="px-3 py-2">Загружен</th>
                  <th className="px-3 py-2">Удалён</th>
                  <th className="px-3 py-2">Действия</th>
                </tr>
              </thead>
              <tbody>
                {kbDocs.map((doc) => (
                  <tr key={doc.id} className="border-t border-[var(--line)]">
                    <td className="px-3 py-2">{doc.source_name}</td>
                    <td className="px-3 py-2">{parseFileExt(doc.source_name)}</td>
                    <td className="px-3 py-2">{doc.source_type}</td>
                    <td className="px-3 py-2">{doc.current_version}</td>
                    <td className="px-3 py-2">{toHumanDate(doc.created_at)}</td>
                    <td className="px-3 py-2">{toHumanDate(doc.deleted_at)}</td>
                    <td className="px-3 py-2">
                      <button
                        className="btn px-2 py-1 text-xs"
                        onClick={() => onDeleteKbDocument(doc.id)}
                        disabled={Boolean(doc.deleted_at)}
                      >
                        <Trash2 size={13} />
                        Удалить
                      </button>
                    </td>
                  </tr>
                ))}

                {kbDocs.length === 0 ? (
                  <tr>
                    <td className="px-3 py-6 text-sm text-[var(--muted)]" colSpan={7}>
                      Список документов пуст.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <div className="mt-2 flex items-center justify-between">
            <button
              className="btn inline-flex items-center gap-1 text-sm"
              disabled={kbPage <= 1 || isKbLoading}
              onClick={() => setKbPage((prev) => Math.max(1, prev - 1))}
            >
              <ChevronLeft size={14} />
              Назад
            </button>

            <div className="text-xs text-[var(--muted)]">
              Страница {kbPage} • всего {kbTotal}
            </div>

            <button
              className="btn inline-flex items-center gap-1 text-sm"
              disabled={kbPage * PAGE_SIZE >= kbTotal || isKbLoading}
              onClick={() => setKbPage((prev) => prev + 1)}
            >
              Вперёд
              <ChevronRight size={14} />
            </button>
          </div>
        </section>
      ) : null}

      {section === 'settings' ? (
        <section className="surface fade-in-up min-h-[540px] p-3">
          <div className="mb-3 text-sm font-semibold">Настройки</div>

          <div className="grid gap-3 lg:grid-cols-2">
            <div className="soft-surface p-3">
              <div className="mb-2 text-sm font-medium">Настройки backend</div>

              <label className="mb-1 block text-xs text-[var(--muted)]">
                Режим по умолчанию для новых тикетов
              </label>
              <select
                className="field"
                value={defaultModeSetting}
                onChange={(event) => setDefaultModeSetting(event.target.value as ChatModeCode)}
              >
                <option value="full_ai">AI ведёт диалог</option>
                <option value="ai_assist">AI помогает оператору</option>
                <option value="no_ai">Без AI</option>
              </select>

              <button className="btn btn-primary mt-2" onClick={onSaveDefaultMode}>
                {settingsSaveState === 'saving' ? 'Сохраняем...' : 'Сохранить в API'}
              </button>

              {settingsSaveState === 'saved' ? (
                <div className="mt-2 text-xs text-[var(--success)]">Сохранено</div>
              ) : null}
              {settingsSaveState === 'error' ? (
                <div className="mt-2 text-xs text-[var(--danger)]">Ошибка сохранения</div>
              ) : null}
            </div>

            <div className="soft-surface p-3">
              <div className="mb-2 text-sm font-medium">Локальные настройки MVP</div>

              <label className="mb-1 block text-xs text-[var(--muted)]">
                Автозакрытие через (минут)
              </label>
              <input
                type="number"
                className="field"
                min={1}
                value={autoCloseMinutes}
                onChange={(event) => setAutoCloseMinutes(Math.max(1, Number(event.target.value) || 1))}
              />

              <label className="mt-2 flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={autoSummaryAfterClose}
                  onChange={(event) => setAutoSummaryAfterClose(event.target.checked)}
                />
                Создавать сводку после закрытия
              </label>

              <label className="mt-1 flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={pushSummaryToRag}
                  onChange={(event) => setPushSummaryToRag(event.target.checked)}
                />
                Отправлять сводку в RAG
              </label>

              <div className="mt-2 text-xs text-[var(--muted)]">
                Эти параметры сохраняются локально и не отправляются в backend.
              </div>
            </div>
          </div>
        </section>
      ) : null}
    </main>
  );
}
