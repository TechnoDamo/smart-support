'use client';

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import {
  Brain,
  ChartColumnBig,
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
  WifiOff,
  MessageSquare
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts';

import { supportApi } from '@/lib/api';
import {
  type AnalyticsReport,
  ApiError,
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

type NavSection = 'inbox' | 'knowledge' | 'settings' | 'analytics';
type StatusFilter = TicketStatusCode | 'all';
type AnalyticsView = 'overview' | 'ai' | 'knowledge';

type ChatRow = {
  chat: Chat;
  activeTicket?: Ticket | null;
  lastMessage?: Message;
  snippet: string;
  lastMessageAt: string;
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

function isBackendConnectivityError(error: unknown): boolean {
  // Ошибки 4xx означают, что backend ответил, значит соединение с ним есть.
  if (error instanceof ApiError) {
    return false;
  }
  return true;
}

const NAV_SECTIONS: ReadonlyArray<{ key: NavSection; label: string }> = [
  { key: 'inbox', label: 'Диалоги' },
  { key: 'knowledge', label: 'База знаний' },
  { key: 'settings', label: 'Настройки' },
  { key: 'analytics', label: 'Аналитика' }
];

const KB_PAGE_SIZE = 20;
const INBOX_FETCH_SIZE = 200;
const POLL_MS = 30000; // 30 seconds instead of 4 seconds
const LOCAL_SETTINGS_KEY = 'smart-support-local-settings-v1';
const CHART_COLORS = ['#2f7df4', '#0f9f65', '#d78a00', '#d14646', '#7a8698'];

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

function toInputDateTime(value: Date) {
  const localDate = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return localDate.toISOString().slice(0, 16);
}

function parseInputDateTime(value?: string) {
  if (!value) return undefined;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return undefined;
  return parsed.toISOString();
}

function toChatTimeLabel(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  const now = new Date();
  const isSameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();

  if (isSameDay) {
    return date.toLocaleTimeString('ru-RU', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  const weekdays = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
  return weekdays[date.getDay()];
}

function formatCompactNumber(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat('ru-RU').format(value);
}

function formatPercent(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${Math.round(value * 100)}%`;
}

function formatDurationShort(totalSeconds?: number | null) {
  if (totalSeconds === null || totalSeconds === undefined || Number.isNaN(totalSeconds)) return '—';
  const seconds = Math.max(0, Math.round(totalSeconds));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (hours > 0) return `${hours}ч ${minutes}м`;
  return `${minutes}м`;
}

function formatTicketStatus(status: TicketStatusCode) {
  if (status === 'pending_ai') return 'Ожидает AI';
  if (status === 'pending_human') return 'Ожидает человека';
  if (status === 'pending_user') return 'Ожидает клиента';
  return 'Без активного тикета';
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

function getRowStatusCode(row: ChatRow): TicketStatusCode {
  return row.activeTicket?.status_code ?? 'closed';
}

function deriveUserDisplay(chat?: Chat) {
  if (!chat) return 'Неизвестный клиент';
  const suffix = chat.user_id.slice(0, 8);
  return `Клиент #${suffix}`;
}

function getPlatformIcon(chat?: Chat) {
  if (!chat) return null;
  
  // Check if it's a Telegram chat (telegram_chat_id is present)
  if (chat.telegram_chat_id) {
    return (
      <div className="flex items-center gap-1 text-xs text-blue-500">
        <MessageSquare size={12} />
        <span>Телеграм</span>
      </div>
    );
  }
  
  return null;
}

function translateMode(mode: ChatModeCode) {
  if (mode === 'full_ai') return 'AI ведёт диалог';
  if (mode === 'ai_assist') return 'AI помогает';
  return 'Без AI';
}

function translateEventLabel(label: string) {
  const modeToText = (modeCode: string) => {
    if (modeCode === 'full_ai') return 'AI ведёт диалог';
    if (modeCode === 'ai_assist') return 'AI помогает';
    if (modeCode === 'no_ai') return 'Без AI';
    return modeCode || 'не задан';
  };

  if (label.startsWith('ticket_status_changed:')) {
    return label
      .replace('ticket_status_changed:', 'Статус тикета:')
      .replace('pending_ai', 'ожидает AI')
      .replace('pending_human', 'ожидает человека')
      .replace('closed', 'закрыт')
      .replace('none', 'не задан');
  }

  if (label.startsWith('chat_mode_changed:')) {
    const nextMode = label.split('->').pop()?.trim() ?? '';
    return `Режим: ${modeToText(nextMode)}`;
  }

  if (label === 'ticket_renamed') return 'Тикет переименован';
  if (label === 'rag_sources_attached') return 'Подтянуты источники из базы знаний';
  if (label === 'ai_suggestions_generated') return 'Сгенерированы AI-подсказки';
  if (label === 'agent_message_sent') return 'Сообщение отправлено';
  if (label.startsWith('chat_mode_set:')) {
    const nextMode = label.replace('chat_mode_set:', '').trim();
    return `Режим: ${modeToText(nextMode)}`;
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

function AnalyticsKpiCard({
  title,
  value,
  hint
}: {
  title: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="soft-surface p-3">
      <div className="text-[11px] uppercase tracking-[0.05em] text-[var(--muted)]">{title}</div>
      <div className="mt-1 text-2xl font-semibold leading-none">{value}</div>
      {hint ? <div className="mt-1 text-xs text-[var(--muted)]">{hint}</div> : null}
    </div>
  );
}

function AnalyticsChartCard({
  title,
  subtitle,
  children
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div className="soft-surface p-3">
      <div className="mb-2">
        <div className="text-sm font-semibold">{title}</div>
        {subtitle ? <div className="text-xs text-[var(--muted)]">{subtitle}</div> : null}
      </div>
      {children}
    </div>
  );
}

export default function SupportWorkspacePage() {
  const [serverStatus, setServerStatus] = useState<ServerStatus>('unknown');
  const [themeMode, setThemeMode] = useState<ThemeMode>('system');

  const [section, setSection] = useState<NavSection>('inbox');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [isChatListOpen, setIsChatListOpen] = useState(true);
  const [isSuggestionsOpen, setIsSuggestionsOpen] = useState(true);
  const [isCompactViewport, setIsCompactViewport] = useState(false);
  const [isChatModalViewport, setIsChatModalViewport] = useState(false);

  const [isLoadingInbox, setIsLoadingInbox] = useState(false);
  const [inboxError, setInboxError] = useState<string | null>(null);
  const [inboxErrorCountdown, setInboxErrorCountdown] = useState(0);
  const [inboxErrorNonce, setInboxErrorNonce] = useState(0);

  const [rawRows, setRawRows] = useState<ChatRow[]>([]);
  const [chatTotal, setChatTotal] = useState(0);
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null);

  const [activeTicketDetails, setActiveTicketDetails] = useState<TicketDetails | null>(null);
  const [chatDetails, setChatDetails] = useState<ChatDetails | null>(null);
  const [isLoadingTicketCard, setIsLoadingTicketCard] = useState(false);

  const [composerText, setComposerText] = useState('');
  const [isSendingMessage, setIsSendingMessage] = useState(false);

  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [isLoadingSuggestions, setIsLoadingSuggestions] = useState(false);
  const [expandedSourcesSuggestionId, setExpandedSourcesSuggestionId] = useState<string | null>(null);

  const [docNameById, setDocNameById] = useState<Record<string, string>>({});

  // Cache for chat details to avoid repeated API calls
  const [chatDetailsCache, setChatDetailsCache] = useState<Record<string, { details: ChatDetails; timestamp: number }>>({});

  const [kbPage, setKbPage] = useState(1);
  const [kbIncludeDeleted, setKbIncludeDeleted] = useState(false);
  const [kbDocs, setKbDocs] = useState<RagDocument[]>([]);
  const [kbTotal, setKbTotal] = useState(0);
  const [kbError, setKbError] = useState<string | null>(null);
  const [isKbLoading, setIsKbLoading] = useState(false);
  const [isKbUploading, setIsKbUploading] = useState(false);
  const [ingestionStatusMap, setIngestionStatusMap] = useState<Record<string, string>>({});

  const [analyticsFromInput, setAnalyticsFromInput] = useState(() =>
    toInputDateTime(new Date(Date.now() - 7 * 24 * 60 * 60 * 1000))
  );
  const [analyticsToInput, setAnalyticsToInput] = useState(() => toInputDateTime(new Date()));
  const [analyticsReport, setAnalyticsReport] = useState<AnalyticsReport | null>(null);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);
  const [isAnalyticsLoading, setIsAnalyticsLoading] = useState(false);
  const [analyticsView, setAnalyticsView] = useState<AnalyticsView>('overview');
  const [isAnalyticsRangeOpen, setIsAnalyticsRangeOpen] = useState(false);

  const [defaultModeSetting, setDefaultModeSetting] = useState<ChatModeCode>('ai_assist');
  const [settingsSaveState, setSettingsSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [autoCloseMinutes, setAutoCloseMinutes] = useState(30);
  const [autoSummaryAfterClose, setAutoSummaryAfterClose] = useState(true);
  const [pushSummaryToRag, setPushSummaryToRag] = useState(false);

  const timelineRef = useRef<HTMLDivElement | null>(null);
  const shouldJumpToBottomRef = useRef(false);
  const lastSeenMessageKeyByChatRef = useRef<Record<string, string>>({});

  const api = supportApi;

  const showInboxError = useCallback((message: string) => {
    setInboxError(message);
    setInboxErrorNonce((prev) => prev + 1);
  }, []);

  const selectedRow = useMemo(() => {
    if (!selectedChatId) return null;
    return rawRows.find((row) => row.chat.id === selectedChatId) ?? null;
  }, [rawRows, selectedChatId]);

  const selectedActiveTicketId = selectedRow?.chat.active_ticket_id ?? null;
  const isSelectedChatReadOnly = !selectedActiveTicketId;

  const activeSectionIndex = useMemo(
    () => Math.max(0, NAV_SECTIONS.findIndex((item) => item.key === section)),
    [section]
  );

  const filteredRows = useMemo(() => {
    let rows = [...rawRows];

    if (statusFilter !== 'all') {
      rows = rows.filter((row) => getRowStatusCode(row) === statusFilter);
    }

    const normalizedSearch = search.trim().toLowerCase();
    if (normalizedSearch) {
      rows = rows.filter((row) => {
        const haystack = [
          row.chat.id,
          row.activeTicket?.id,
          row.activeTicket?.title,
          row.activeTicket?.summary,
          row.lastMessage?.text,
          getRowStatusCode(row),
          row.chat.channel.code,
          row.chat.channel.name
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();

        return haystack.includes(normalizedSearch);
      });
    }

    rows.sort((a, b) => new Date(b.lastMessageAt).getTime() - new Date(a.lastMessageAt).getTime());
    return rows;
  }, [rawRows, statusFilter, search]);

  const timelineItems = useMemo<TimelineItem[]>(() => {
    if (!selectedChatId) return [];

    const messages = chatDetails?.messages ?? [];
    const modeEvents = chatDetails?.mode_events ?? [];

    const all: TimelineItem[] = [];

    for (const message of messages) {
      all.push({
        id: `msg-${message.id}`,
        kind: 'message',
        ts: message.time,
        message
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

    all.sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());
    return all;
  }, [chatDetails?.messages, chatDetails?.mode_events, selectedChatId]);

  const selectedChatMessages = useMemo(() => chatDetails?.messages ?? [], [chatDetails?.messages]);

  const kbCounters = useMemo(() => {
    const values = Object.values(ingestionStatusMap);
    return {
      queued: values.filter((value) => value === 'queued').length,
      processing: values.filter((value) => value === 'processing').length,
      done: values.filter((value) => value === 'done').length,
      failed: values.filter((value) => value === 'failed').length
    };
  }, [ingestionStatusMap]);

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
        const now = Date.now();
        const chatsResponse = await api.listChats({ page: 1, page_size: INBOX_FETCH_SIZE });
        const uniqueChatIds = chatsResponse.items.map((chat) => chat.id);
        const uniqueActiveTicketIds = Array.from(
          new Set(
            chatsResponse.items
              .map((chat) => chat.active_ticket_id)
              .filter((ticketId): ticketId is string => Boolean(ticketId))
          )
        );

        const chatDetailsMap: Record<string, ChatDetails> = {};
        const missingChatIds = new Set<string>();
        const chatIdsToFetch: string[] = [];

        for (const chatId of uniqueChatIds) {
          const cached = chatDetailsCache[chatId];
          if (cached && (now - cached.timestamp < 60000)) {
            chatDetailsMap[chatId] = cached.details;
          } else {
            chatIdsToFetch.push(chatId);
          }
        }

        if (chatIdsToFetch.length > 0) {
          const chatDetailSettled = await Promise.allSettled(
            chatIdsToFetch.map((chatId) =>
              api
                .getChat(chatId)
                .then((details) => ({ chatId, details }))
                .catch((error) => Promise.reject({ chatId, error }))
            )
          );

          const newCacheEntries: Record<string, { details: ChatDetails; timestamp: number }> = {};

          for (const result of chatDetailSettled) {
            if (result.status === 'fulfilled') {
              const { chatId, details } = result.value;
              chatDetailsMap[chatId] = details;
              newCacheEntries[chatId] = { details, timestamp: now };
              continue;
            }

            const wrapped = result.reason as { chatId?: string; error?: unknown };
            if (wrapped.chatId && wrapped.error instanceof ApiError && wrapped.error.status === 404) {
              missingChatIds.add(wrapped.chatId);
            }
          }

          if (Object.keys(newCacheEntries).length > 0) {
            setChatDetailsCache(prev => ({ ...prev, ...newCacheEntries }));
          }
        }

        const activeTicketMap: Record<string, TicketDetails> = {};
        if (uniqueActiveTicketIds.length > 0) {
          const ticketSettled = await Promise.allSettled(
            uniqueActiveTicketIds.map((ticketId) =>
              api.getTicket(ticketId).then((ticket) => ({ ticketId, ticket }))
            )
          );

          for (const result of ticketSettled) {
            if (result.status === 'fulfilled') {
              activeTicketMap[result.value.ticketId] = result.value.ticket;
            }
          }
        }

        const rows: ChatRow[] = chatsResponse.items.flatMap((chat) => {
          if (missingChatIds.has(chat.id)) {
            return [];
          }

          const chatDetail = chatDetailsMap[chat.id];
          const lastMessage = (chatDetail?.messages ?? []).at(-1);
          const activeTicket =
            chat.active_ticket_id ? activeTicketMap[chat.active_ticket_id] ?? null : null;
          const lastMessageAt =
            lastMessage?.time ?? chatDetail?.updated_at ?? activeTicket?.time_started ?? chat.updated_at;

          return [
            {
              chat,
              activeTicket,
              lastMessage,
              lastMessageAt,
              snippet: lastMessage?.text ?? activeTicket?.summary ?? activeTicket?.title ?? 'Нет сообщений'
            }
          ];
        });

        rows.sort((a, b) => new Date(b.lastMessageAt).getTime() - new Date(a.lastMessageAt).getTime());

        setRawRows(rows);
        setChatTotal(chatsResponse.total);

        if (rows.length > 0) {
          const hasCurrentSelection = Boolean(selectedChatId) && rows.some((row) => row.chat.id === selectedChatId);
          const nextSelectedChatId = hasCurrentSelection ? selectedChatId : rows[0].chat.id;
          if (nextSelectedChatId && nextSelectedChatId !== selectedChatId) {
            shouldJumpToBottomRef.current = true;
          }
          setSelectedChatId(nextSelectedChatId);
        } else {
          setSelectedChatId(null);
        }

        setServerStatus('online');
      } catch (error) {
        if (error instanceof ApiError) {
          showInboxError(error.message);
        } else {
          showInboxError('Не удалось загрузить список чатов');
        }

        if (isBackendConnectivityError(error)) {
          setServerStatus('offline');
        }
      } finally {
        if (!silent) {
          setIsLoadingInbox(false);
        }
      }
    },
    [api, selectedChatId, chatDetailsCache, showInboxError]
  );

  const loadChatCard = useCallback(
    async (chatId: string, silent = false) => {
      const row = rawRows.find((item) => item.chat.id === chatId);
      if (!row) {
        setActiveTicketDetails(null);
        setChatDetails(null);
        return;
      }

      if (!silent) {
        setIsLoadingTicketCard(true);
      }

      try {
        const chatResponse = await api.getChat(chatId);
        let ticketResponse: TicketDetails | null = null;

        if (row.chat.active_ticket_id) {
          try {
            ticketResponse = await api.getTicket(row.chat.active_ticket_id);
          } catch (error) {
            if (!(error instanceof ApiError && error.status === 404)) {
              throw error;
            }
          }
        }

        setActiveTicketDetails(ticketResponse);
        setChatDetails(chatResponse);

        setServerStatus('online');
      } catch (error) {
        if (!silent) {
          showInboxError(error instanceof Error ? error.message : 'Не удалось открыть диалог');
        }

        if (error instanceof ApiError && error.status === 404) {
          setActiveTicketDetails(null);
          setChatDetails(null);
          setSelectedChatId((current) => (current === chatId ? null : current));
          setRawRows((prev) => prev.filter((item) => item.chat.id !== chatId));
          return;
        }

        if (isBackendConnectivityError(error)) {
          setServerStatus('offline');
        }
      } finally {
        if (!silent) {
          setIsLoadingTicketCard(false);
        }
      }
    },
    [api, rawRows, showInboxError]
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
          page_size: KB_PAGE_SIZE,
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

  const loadAnalytics = useCallback(
    async (silent = false) => {
      if (!silent) {
        setIsAnalyticsLoading(true);
      }
      setAnalyticsError(null);

      try {
        const response = await api.getAnalyticsReport({
          from: parseInputDateTime(analyticsFromInput),
          to: parseInputDateTime(analyticsToInput)
        });
        setAnalyticsReport(response);
      } catch (error) {
        setAnalyticsError(error instanceof Error ? error.message : 'Не удалось загрузить аналитику');
      } finally {
        if (!silent) {
          setIsAnalyticsLoading(false);
        }
      }
    },
    [analyticsFromInput, analyticsToInput, api]
  );

  const onApplyAnalyticsPreset = useCallback((days: number) => {
    const now = new Date();
    const from = new Date(now.getTime() - days * 24 * 60 * 60 * 1000);
    setAnalyticsFromInput(toInputDateTime(from));
    setAnalyticsToInput(toInputDateTime(now));
  }, []);

  const ANALYTICS_VIEWS: ReadonlyArray<{ key: AnalyticsView; label: string }> = useMemo(
    () => [
      { key: 'overview', label: 'Обзор' },
      { key: 'ai', label: 'AI' },
      { key: 'knowledge', label: 'База знаний' }
    ],
    []
  );

  const activeAnalyticsViewIndex = useMemo(
    () => Math.max(0, ANALYTICS_VIEWS.findIndex((tab) => tab.key === analyticsView)),
    [ANALYTICS_VIEWS, analyticsView]
  );

  const analyticsTicketStatusData = useMemo(() => {
    if (!analyticsReport) return [];
    return [
      { name: 'Ожидают AI', value: analyticsReport.tickets.by_status.pending_ai },
      { name: 'Ожидают человека', value: analyticsReport.tickets.by_status.pending_human },
      { name: 'Закрытые', value: analyticsReport.tickets.by_status.closed }
    ];
  }, [analyticsReport]);

  const analyticsMessagesData = useMemo(() => {
    if (!analyticsReport) return [];
    return [
      { name: 'Клиент', value: analyticsReport.messages.by_entity.user },
      { name: 'AI', value: analyticsReport.messages.by_entity.ai_operator },
      { name: 'Оператор', value: analyticsReport.messages.by_entity.operator }
    ];
  }, [analyticsReport]);

  const analyticsAiRatesData = useMemo(() => {
    if (!analyticsReport) return [];
    return [
      { name: 'Закрыто AI', value: Math.round(analyticsReport.ai_performance.resolution_rate * 100) },
      { name: 'Передано человеку', value: Math.round(analyticsReport.ai_performance.escalation_rate * 100) }
    ];
  }, [analyticsReport]);

  const analyticsModeData = useMemo(() => {
    if (!analyticsReport) return [];
    return [
      { name: 'AI ведёт', value: analyticsReport.ai_performance.chat_mode_distribution.full_ai },
      { name: 'AI помогает', value: analyticsReport.ai_performance.chat_mode_distribution.ai_assist },
      { name: 'Без AI', value: analyticsReport.ai_performance.chat_mode_distribution.no_ai }
    ];
  }, [analyticsReport]);

  const analyticsIngestionData = useMemo(() => {
    if (!analyticsReport) return [];
    return [
      { name: 'В очереди', value: analyticsReport.rag.ingestion_jobs.queued },
      { name: 'Обработка', value: analyticsReport.rag.ingestion_jobs.processing },
      { name: 'Готово', value: analyticsReport.rag.ingestion_jobs.done },
      { name: 'Ошибки', value: analyticsReport.rag.ingestion_jobs.failed }
    ];
  }, [analyticsReport]);

  const analyticsUserData = useMemo(() => {
    if (!analyticsReport) return [];
    return [
      { name: 'Новые', value: analyticsReport.users.new_in_period },
      { name: 'Возвраты', value: analyticsReport.users.returning_users_in_period }
    ];
  }, [analyticsReport]);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const params = new URLSearchParams(window.location.search);
    const sectionParam = params.get('section');
    const statusParam = params.get('status');
    const qParam = params.get('q');

    if (sectionParam === 'inbox' || sectionParam === 'knowledge' || sectionParam === 'settings' || sectionParam === 'analytics') {
      setSection(sectionParam);
    }
    if (
      statusParam === 'all' ||
      statusParam === 'pending_ai' ||
      statusParam === 'pending_human' ||
      statusParam === 'pending_user' ||
      statusParam === 'closed'
    ) {
      setStatusFilter(statusParam);
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
      params.set('status', statusFilter);
      if (search.trim()) {
        params.set('q', search.trim());
      }
    }

    const nextUrl = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState({}, '', nextUrl);
  }, [section, statusFilter, search]);

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
    if (!inboxError) {
      setInboxErrorCountdown(0);
      return;
    }

    setInboxErrorCountdown(3);

    const intervalId = window.setInterval(() => {
      setInboxErrorCountdown((prev) => Math.max(0, prev - 1));
    }, 1000);

    const timeoutId = window.setTimeout(() => {
      setInboxError(null);
      setInboxErrorCountdown(0);
    }, 3000);

    return () => {
      window.clearInterval(intervalId);
      window.clearTimeout(timeoutId);
    };
  }, [inboxError, inboxErrorNonce]);

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
    if (typeof window === 'undefined') return;

    const suggestionsQuery = window.matchMedia('(max-width: 1279px)');
    const chatQuery = window.matchMedia('(max-width: 1023px)');
    const applyViewport = () => {
      const isSuggestionsCompact = suggestionsQuery.matches;
      const isChatCompact = chatQuery.matches;
      setIsCompactViewport(isSuggestionsCompact);
      setIsChatModalViewport(isChatCompact);

      if (isSuggestionsCompact) {
        setIsSuggestionsOpen(false);
      } else {
        setIsSuggestionsOpen(true);
      }

      if (isChatCompact) {
        setIsChatListOpen(false);
      } else {
        setIsChatListOpen(true);
      }
    };

    applyViewport();
    const onChange = () => applyViewport();
    suggestionsQuery.addEventListener('change', onChange);
    chatQuery.addEventListener('change', onChange);
    return () => {
      suggestionsQuery.removeEventListener('change', onChange);
      chatQuery.removeEventListener('change', onChange);
    };
  }, []);

  useEffect(() => {
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
  }, []);

  useEffect(() => {
    loadInbox();
    ensureDocNames();
  }, [loadInbox, ensureDocNames]);

  useEffect(() => {
    if (section !== 'inbox') return;
    if (!selectedChatId) {
      setActiveTicketDetails(null);
      setChatDetails(null);
      return;
    }

    const selectedStillExists = rawRows.some((row) => row.chat.id === selectedChatId);
    if (!selectedStillExists) {
      setActiveTicketDetails(null);
      setChatDetails(null);
      return;
    }

    loadChatCard(selectedChatId);
  }, [selectedChatId, rawRows, loadChatCard, section]);

  useEffect(() => {
    if (section !== 'inbox') return;

    const timer = window.setInterval(() => {
      loadInbox(true);
    }, POLL_MS);

    return () => window.clearInterval(timer);
  }, [loadInbox, section]);

  useEffect(() => {
    if (section !== 'knowledge') return;
    loadKnowledgeBase();
  }, [section, loadKnowledgeBase]);

  useEffect(() => {
    if (section !== 'analytics') return;
    loadAnalytics();
  }, [section, loadAnalytics]);

  useEffect(() => {
    if (filteredRows.length === 0) {
      setSelectedChatId(null);
      return;
    }

    if (!selectedChatId || !filteredRows.some((item) => item.chat.id === selectedChatId)) {
      shouldJumpToBottomRef.current = true;
      setSelectedChatId(filteredRows[0].chat.id);
    }
  }, [filteredRows, selectedChatId]);

  useEffect(() => {
    if (!selectedChatId || isLoadingTicketCard || !shouldJumpToBottomRef.current) return;
    if (!selectedRow || !chatDetails || chatDetails.id !== selectedRow.chat.id) return;
    const el = timelineRef.current;
    if (!el) return;
    const rafId = window.requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
      shouldJumpToBottomRef.current = false;
    });
    return () => window.cancelAnimationFrame(rafId);
  }, [chatDetails, isLoadingTicketCard, selectedRow, selectedChatId, timelineItems]);

  useEffect(() => {
    if (!selectedChatId || !selectedRow || !chatDetails) return;
    if (chatDetails.id !== selectedRow.chat.id) return;

    const lastMessage = selectedChatMessages[selectedChatMessages.length - 1];
    const nextKey = lastMessage ? `${lastMessage.id}:${lastMessage.entity}` : '';
    const prevKey = lastSeenMessageKeyByChatRef.current[selectedChatId];

    if (!prevKey) {
      lastSeenMessageKeyByChatRef.current[selectedChatId] = nextKey;
      return;
    }

    if (!nextKey || prevKey === nextKey) return;
    lastSeenMessageKeyByChatRef.current[selectedChatId] = nextKey;

    if (lastMessage.entity !== 'operator' && lastMessage.entity !== 'user') return;
    const el = timelineRef.current;
    if (!el) return;

    const rafId = window.requestAnimationFrame(() => {
      el.scrollTo({
        top: el.scrollHeight,
        behavior: 'smooth'
      });
    });

    return () => window.cancelAnimationFrame(rafId);
  }, [chatDetails, selectedRow, selectedChatId, selectedChatMessages]);

  const onManualRefresh = useCallback(async () => {
    await loadInbox(false);
  }, [loadInbox]);

  const ensureRagDocumentsAvailable = useCallback(async (): Promise<boolean> => {
    try {
      const response = await api.listRagDocuments({
        page: 1,
        page_size: 1,
        include_deleted: false
      });

      if (response.total > 0) {
        return true;
      }

      showInboxError('Нет загруженных документов');
      return false;
    } catch (error) {
      showInboxError(error instanceof Error ? error.message : 'Не удалось проверить документы');
      return false;
    }
  }, [api, showInboxError]);

  const onChangeChatMode = useCallback(
    async (nextMode: ChatModeCode, reason: string) => {
      if (!selectedRow) return;
      if (nextMode === 'full_ai') {
        const hasDocuments = await ensureRagDocumentsAvailable();
        if (!hasDocuments) return;
      }

      try {
        await api.changeChatMode(selectedRow.chat.id, {
          to_mode_code: nextMode,
          reason
        });

        await loadInbox(true);
        await loadChatCard(selectedRow.chat.id, true);
      } catch (error) {
        showInboxError(error instanceof Error ? error.message : 'Не удалось сменить режим чата');
      }
    },
    [api, ensureRagDocumentsAvailable, loadInbox, loadChatCard, selectedRow, showInboxError]
  );

  const onGenerateSuggestions = useCallback(async () => {
    if (!selectedRow) return;
    if (!selectedActiveTicketId) {
      showInboxError('В этом чате нет активного тикета для AI-подсказок');
      return;
    }
    const hasDocuments = await ensureRagDocumentsAvailable();
    if (!hasDocuments) {
      return;
    }

    try {
      setIsLoadingSuggestions(true);
      setIsSuggestionsOpen(true);
      const response = await api.getSuggestions(selectedRow.chat.id, {
        ticket_id: selectedActiveTicketId,
        draft_context: composerText.trim() || undefined,
        max_suggestions: 5
      });

      setSuggestions(response.suggestions);
      setExpandedSourcesSuggestionId(null);
    } catch (error) {
      showInboxError(error instanceof Error ? error.message : 'Не удалось получить AI-подсказки');
    } finally {
      setIsLoadingSuggestions(false);
    }
  }, [api, composerText, ensureRagDocumentsAvailable, selectedActiveTicketId, selectedRow, showInboxError]);

  const onUseSuggestion = useCallback((text: string) => {
    setComposerText((prev) => {
      if (!prev.trim()) return text.trim();
      return `${prev.trim()}\n\n${text.trim()}`;
    });
  }, []);

  const onToggleSuggestionSources = useCallback((suggestionId: string) => {
    setExpandedSourcesSuggestionId((current) => (current === suggestionId ? null : suggestionId));
  }, []);

  const sendMessageText = useCallback(
    async (text: string) => {
      if (!selectedRow || !text.trim()) return;
      if (!selectedActiveTicketId) {
        showInboxError('В этом чате нет активного тикета для ответа');
        return;
      }

      try {
        setIsSendingMessage(true);

        await api.sendMessage(selectedRow.chat.id, {
          ticket_id: selectedActiveTicketId,
          text: text.trim()
        });

        setComposerText('');

        await loadChatCard(selectedRow.chat.id, true);
        await loadInbox(true);
      } catch (error) {
        showInboxError(error instanceof Error ? error.message : 'Не удалось отправить сообщение');
      } finally {
        setIsSendingMessage(false);
      }
    },
    [api, loadInbox, loadChatCard, selectedActiveTicketId, selectedRow, showInboxError]
  );

  const onSendMessage = useCallback(async () => {
    await sendMessageText(composerText);
  }, [composerText, sendMessageText]);

  const onSendSuggestionNow = useCallback(
    async (text: string) => {
      await sendMessageText(text);
    },
    [sendMessageText]
  );

  const onComposerKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        if (!isSendingMessage && composerText.trim()) {
          void onSendMessage();
        }
      }
    },
    [composerText, isSendingMessage, onSendMessage]
  );

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

  const chatListContent = (
    <>
      <div
        className={`mb-3 grid items-center gap-2 ${
          !isChatModalViewport ? 'grid-cols-[minmax(0,1fr)_auto]' : 'grid-cols-1'
        }`}
      >
        <div className="text-sm font-semibold">Чаты</div>
        {!isChatModalViewport ? (
          <button
            className="btn btn-primary inline-flex h-7 w-7 items-center justify-center self-center text-white"
            style={{ padding: 0 }}
            onClick={() => setIsChatListOpen(false)}
            aria-label="Свернуть чаты"
          >
            <svg viewBox="0 0 24 24" className="h-3 w-3 text-white" aria-hidden="true">
              <path
                d="M15.5 4.5 8.5 12l7 7.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="3.4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        ) : null}
      </div>

      <div className="mb-3 grid grid-cols-1 gap-2">
       
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_auto]">
       
        <label className="relative ">
          <input
            className="field !border !border-[rgba(47,125,244,0.36)] pl-8"
             placeholder="Поиск по чатам"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>

          <button className="btn justify-center" onClick={onManualRefresh} aria-label="Обновить">
            <RefreshCcw size={14} />
          </button>
        </div>
      </div>

       <div className="mb-2 flex items-center justify-between text-xs text-[var(--muted)]">
        <div>Чаты: {filteredRows.length} из {chatTotal}</div>
         {isLoadingInbox ? (
           <div className="inline-flex items-center gap-1">
             <Loader2 size={13} className="animate-spin" />
             Loading...
           </div>
         ) : null}
      </div>

      <div className="scrollbar-thin flex-1 space-y-2 overflow-y-auto pr-1">
        {filteredRows.map((row) => {
          const isActive = selectedChatId === row.chat.id;
          const statusCode = getRowStatusCode(row);
          const isClosed = statusCode === 'closed';
          const aiAutoReply = row.chat.mode_code === 'full_ai' && !isClosed;

          return (
            <button
              key={row.chat.id}
              className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                isActive
                  ? 'border-[var(--accent)] bg-[var(--accent-soft)]'
                  : 'border-[var(--line)] bg-[var(--panel-solid)] hover:bg-[var(--bg-soft)]'
              } ${statusCode === 'pending_ai' ? 'status-pulse' : ''}`}
              onClick={() => {
                shouldJumpToBottomRef.current = true;
                setSelectedChatId(row.chat.id);
                if (isChatModalViewport) {
                  setIsChatListOpen(false);
                }
              }}
            >
              <div className="mb-2 flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold">{deriveUserDisplay(row.chat)}</div>
                  {getPlatformIcon(row.chat)}
                </div>
                <div className="flex items-center gap-2">
                  <span className="badge badge-muted">{toChatTimeLabel(row.lastMessageAt)}</span>
                  {aiAutoReply ? <span className="ai-dot" title="AI отвечает автоматически" /> : null}
                </div>
              </div>

              <div className="line-clamp-2 text-sm text-[var(--muted)]">{row.snippet}</div>
            </button>
          );
        })}

         {filteredRows.length === 0 ? (
           <div className="rounded-xl bg-[var(--bg-soft)] p-4 text-sm text-[var(--muted)]">
             Чаты не найдены.
           </div>
         ) : null}
      </div>
    </>
  );

  const suggestionsContent = (
    <>
      <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.06em] text-[var(--muted)]">Варианты ответа</div>

      {isLoadingSuggestions ? (
        <div className="mb-2 inline-flex items-center gap-2 text-xs text-[var(--muted)]">
          <Loader2 size={13} className="animate-spin" />
          Генерируем рекомендации...
        </div>
      ) : null}

      {!isLoadingSuggestions && suggestions.length === 0 ? (
        <div className="rounded-xl bg-[var(--panel-solid)] px-3 py-2 text-xs text-[var(--muted)]">
          Нажмите кнопку AI в поле ввода, чтобы получить варианты.
        </div>
      ) : null}

      <div className="scrollbar-thin max-h-full space-y-2 overflow-y-auto pr-1">
        {suggestions.map((suggestion, index) => (
          <div key={suggestion.id} className="rounded-xl border border-[var(--line)] bg-[var(--panel-solid)] p-2">
            <div className="mb-2 whitespace-pre-wrap text-sm leading-5 text-[var(--text)]">{suggestion.text}</div>

            <div className="flex flex-wrap items-center gap-2">
              <button className="btn px-2.5 py-1.5 text-xs" onClick={() => onUseSuggestion(suggestion.text)}>
                Вставить в ответ
              </button>
              <button
                className="btn btn-primary px-2.5 py-1.5 text-xs"
                onClick={() => onSendSuggestionNow(suggestion.text)}
                disabled={isSendingMessage || isSelectedChatReadOnly}
              >
                Отправить сразу
              </button>
              <button className="btn px-2.5 py-1.5 text-xs" onClick={() => onToggleSuggestionSources(suggestion.id)}>
                Источник {index + 1}
              </button>
            </div>

            {expandedSourcesSuggestionId === suggestion.id ? (
              <div className="mt-2 space-y-2">
                {(suggestion.citations ?? []).map((citation) => (
                  <div key={`${suggestion.id}-${citation.chunk_id}`} className="rounded-lg bg-[var(--bg-soft)] p-2 text-xs">
                    <div>Документ: {docNameById[citation.document_id] ?? citation.document_id}</div>
                    <div>Фрагмент: {citation.chunk_id}</div>
                    <div>Оценка: {citation.score.toFixed(3)}</div>
                  </div>
                ))}
                {(suggestion.citations ?? []).length === 0 ? (
                  <div className="rounded-lg bg-[var(--bg-soft)] p-2 text-xs text-[var(--muted)]">
                    Для этого варианта источники не найдены.
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </>
  );

  return (
    <main className="mx-auto max-w-[1680px] px-3 pb-4 pt-4 sm:px-4 sm:pt-5 lg:px-6">
      <header className="surface fade-in-up mb-3 p-2">
        <div className="flex items-center justify-between gap-2 overflow-x-auto whitespace-nowrap">
          <div className="inline-flex items-center gap-2">
            <div className="px-1 text-sm font-semibold">Смарт Поддержка</div>
            <div className="relative rounded-xl bg-[var(--bg-soft)] p-1">
              <span
                className="pointer-events-none absolute bottom-1 left-1 top-1 rounded-lg bg-[var(--accent)] shadow-[0_8px_20px_rgba(47,125,244,0.3)] transition-transform duration-300 ease-out"
                style={{
                  width: `calc((100% - 8px) / ${NAV_SECTIONS.length})`,
                  transform: `translateX(${activeSectionIndex * 100}%)`
                }}
              />
              <div
                className="relative z-10 grid"
                style={{ gridTemplateColumns: `repeat(${NAV_SECTIONS.length}, minmax(0, 1fr))` }}
              >
                {NAV_SECTIONS.map((item) => (
                  <button
                    key={item.key}
                    className={`inline-flex items-center justify-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors duration-200 ${
                      section === item.key ? 'text-white' : 'text-[var(--muted)] hover:text-[var(--text)]'
                    }`}
                    onClick={() => setSection(item.key)}
                  >
                    {item.key === 'inbox' ? <MessageCircle size={13} /> : null}
                    {item.key === 'knowledge' ? <FileText size={13} /> : null}
                    {item.key === 'settings' ? <Settings size={13} /> : null}
                    {item.key === 'analytics' ? <ChartColumnBig size={13} /> : null}
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="inline-flex items-center gap-2">
            <div className="soft-surface flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-[var(--muted)]">
              {serverStatus === 'online' ? <Wifi size={13} /> : <WifiOff size={13} />}
              {serverStatus === 'online' ? 'Онлайн' : serverStatus === 'offline' ? 'Офлайн' : 'Проверка'}
            </div>

            <ThemeToggle theme={themeMode} onChange={setThemeMode} />
          </div>
        </div>
      </header>

      {inboxError ? (
        <div className="mb-3 rounded-xl bg-[rgba(209,70,70,0.13)] px-3 py-2 text-sm text-[var(--danger)]">
          {inboxError}
          {inboxErrorCountdown > 0 ? ` (скроется через ${inboxErrorCountdown}с)` : ''}
        </div>
      ) : null}

      {section === 'inbox' ? (
        <div className="relative h-[calc(100dvh-150px)] min-h-[560px]">
          <div
            className={`grid h-full min-h-0 transition-[grid-template-columns,gap] duration-300 ${
              isChatModalViewport ? 'grid-cols-1 gap-0' : 'gap-2 lg:grid-cols-[auto_minmax(0,1fr)]'
            }`}
          >
            <div
              className={`hidden overflow-hidden pr-2 transition-[width,padding] duration-300 lg:block ${
                isChatListOpen ? 'w-[320px]' : 'w-[56px]'
              }`}
            >
              <section className="surface relative flex h-full min-h-0 w-full overflow-hidden">
                <div
                  className={`absolute inset-0 flex min-h-0 flex-col p-3 transition-[opacity,transform] duration-300 ease-in-out ${
                    isChatListOpen ? 'translate-x-0 opacity-100 z-10' : '-translate-x-2 opacity-0 pointer-events-none z-0'
                  }`}
                >
                  {chatListContent}
                </div>

                <div
                  className={`absolute inset-0 flex min-h-0 flex-col p-1.5 transition-[opacity,transform] duration-300 ease-in-out ${
                    isChatListOpen ? 'translate-x-2 opacity-0 pointer-events-none z-0' : 'translate-x-0 opacity-100 z-10'
                  }`}
                >
                  <button
                    className="btn btn-primary mx-auto mt-1 inline-flex h-7 w-7 items-center justify-center text-white"
                    style={{ padding: 0 }}
                    onClick={() => setIsChatListOpen(true)}
                    aria-label="Развернуть чаты"
                  >
                    <svg viewBox="0 0 24 24" className="h-3 w-3 text-white" aria-hidden="true">
                      <path
                        d="M8.5 4.5 15.5 12l-7 7.5"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="3.4"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </button>

                  <div className="scrollbar-thin mt-2 flex flex-1 flex-col items-center gap-2 overflow-y-auto pb-1 pt-1">
                    {filteredRows.map((row) => {
                      const isActive = selectedChatId === row.chat.id;
                      const avatar = (row.chat.user_id?.[0] ?? '?').toUpperCase();
                      const statusCode = getRowStatusCode(row);
                      const statusClass =
                        statusCode === 'closed'
                          ? 'border-[var(--danger)]'
                          : statusCode === 'pending_human'
                            ? 'border-[var(--success)]'
                            : 'border-[var(--accent)]';
                      const hasUnread = statusCode !== 'closed';

                      return (
                        <button
                          key={`mini-${row.chat.id}`}
                          className={`relative flex h-9 w-9 items-center justify-center rounded-full border text-[11px] font-semibold ${
                            isActive
                              ? 'bg-[var(--accent-soft)] text-[var(--text)]'
                              : 'bg-[var(--panel-solid)] text-[var(--muted)] hover:bg-[var(--bg-soft)]'
                          } ${statusClass}`}
                          title={`${deriveUserDisplay(row.chat)} • ${row.snippet}`}
                          onClick={() => {
                            shouldJumpToBottomRef.current = true;
                            setSelectedChatId(row.chat.id);
                          }}
                          aria-label={`Открыть чат ${deriveUserDisplay(row.chat)}`}
                        >
                          <span>{avatar}</span>
                          {hasUnread ? (
                            <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-[var(--accent)] ring-2 ring-[var(--panel-solid)]" />
                          ) : null}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </section>
            </div>

            <section className="surface fade-in-up min-h-0 overflow-hidden p-3">
            {!selectedRow ? (
              <div className="flex h-full items-center justify-center text-sm text-[var(--muted)]">
                <div className="flex flex-col items-center gap-3">
                  <div>Выберите диалог слева</div>
                  {isChatModalViewport ? (
                    <button className="btn text-xs" onClick={() => setIsChatListOpen(true)}>
                      Открыть чаты
                    </button>
                  ) : null}
                </div>
              </div>
            ) : (
              <div className={`flex h-full min-h-0 ${isSuggestionsOpen ? 'gap-2' : 'gap-0'}`}>
                <div className="flex min-h-0 min-w-0 flex-1 flex-col">
                  <div className="mb-2 rounded-xl bg-[var(--panel-solid)] px-3 py-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <div className="truncate text-sm font-semibold">
                            {activeTicketDetails?.title ?? selectedRow.activeTicket?.title ?? 'История чата'}
                          </div>
                        
                         
                        </div>
                        <div className="mt-0.5 truncate text-xs text-[var(--muted)]">
                          {deriveUserDisplay(chatDetails ?? selectedRow.chat)}
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        {isChatModalViewport ? (
                          <button className="btn px-2.5 py-1.5 text-xs" onClick={() => setIsChatListOpen(true)}>
                            Чаты
                          </button>
                        ) : null}
                        <select
                          className="field h-9 min-w-[155px]  border-2 border-[var(--accent)] bg-[var(--panel-solid)] py-1.5 text-xs font-medium shadow-[0_0_0_1px_rgba(47,125,244,0.24)]"
                          value={(chatDetails ?? selectedRow.chat)?.mode_code ?? 'ai_assist'}
                          onChange={(event) => onChangeChatMode(event.target.value as ChatModeCode, 'mode_selected')}
                        >
                          <option value="full_ai">AI ведёт диалог</option>
                          <option value="no_ai">Без AI</option>
                        </select>

                        <button className="btn px-2.5 py-1.5 text-xs" onClick={() => setIsSuggestionsOpen((prev) => !prev)}>
                          {isSuggestionsOpen ? 'Скрыть варианты' : 'Показать варианты'}
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl bg-[var(--bg-soft)]">
                    <div ref={timelineRef} className="scrollbar-thin flex-1 overflow-y-auto px-3 py-4">
                      <div className="flex w-full flex-col gap-3">
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
                                    <span>{toChatTimeLabel(item.ts)}</span>
                                  </div>
                                  <div className="whitespace-pre-wrap text-sm leading-6">{item.message.text}</div>
                                </div>
                              </div>
                            );
                          }

                          const isModeEvent =
                            item.label.startsWith('chat_mode_changed:') || item.label.startsWith('chat_mode_set:');

                          return (
                            <div key={item.id} className="flex justify-center">
                              <div className="max-w-[80%] rounded-full bg-[var(--panel-solid)] px-3 py-1.5 text-center text-xs text-[var(--muted)]">
                                {isModeEvent
                                  ? translateEventLabel(item.label)
                                  : `${translateEventLabel(item.label)} • ${item.actor} • ${toChatTimeLabel(item.ts)}`}
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
                        {isSelectedChatReadOnly ? (
                          <div className="mb-2 rounded-xl bg-[var(--bg-soft)] px-3 py-2 text-xs text-[var(--muted)]">
                            В этом чате сейчас нет активного тикета. История доступна для просмотра, но отправка ответа и AI-подсказки отключены.
                          </div>
                        ) : null}
                        <div className="flex items-end gap-2">
                          <button
                            className="btn flex gap-1 px-2.5 py-2 text-xs"
                            onClick={onGenerateSuggestions}
                            disabled={isLoadingSuggestions || isSelectedChatReadOnly}
                          >
                            <Brain size={14} />
                            {isLoadingSuggestions ? 'Генерируем...' : 'AI'}
                          </button>

                          <textarea
                            className="min-h-[98px] w-full flex-1 resize-y rounded-xl border border-[var(--line)] bg-transparent px-3 py-2 text-sm text-[var(--text)] outline-none transition focus:border-[var(--accent)] focus:shadow-[0_0_0_2px_rgba(47,125,244,0.2)]"
                            placeholder={isSelectedChatReadOnly ? 'Нет активного тикета для ответа' : 'Введите сообщение клиенту'}
                            value={composerText}
                            onChange={(event) => setComposerText(event.target.value)}
                            onKeyDown={onComposerKeyDown}
                            disabled={isSelectedChatReadOnly}
                          />

                          <button
                            className="btn btn-primary inline-flex items-center gap-1 px-3 py-2 text-xs"
                            onClick={onSendMessage}
                            disabled={isSelectedChatReadOnly || isSendingMessage || !composerText.trim()}
                          >
                            {isSendingMessage ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                            Отправить
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div
                  className={`hidden overflow-hidden transition-[width,opacity,transform] duration-300 xl:block ${
                    isSuggestionsOpen ? 'w-[290px] opacity-100 translate-x-0' : 'w-0 opacity-0 translate-x-6 pointer-events-none'
                  }`}
                >
                  <aside className="soft-surface h-full min-h-0 w-[290px] overflow-hidden p-2">{suggestionsContent}</aside>
                </div>
              </div>
            )}
            </section>
          </div>

          <div
            className={`fixed inset-0 z-30 transition-opacity duration-300 lg:hidden ${
              isChatModalViewport && isChatListOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
            }`}
          >
            <button className="absolute inset-0 bg-black/40" onClick={() => setIsChatListOpen(false)} aria-label="Закрыть список чатов" />
            <div
              className={`absolute left-0 top-0 h-full w-[88vw] max-w-[360px] transform p-2 transition-transform duration-300 ${
                isChatModalViewport && isChatListOpen ? 'translate-x-0' : '-translate-x-full'
              }`}
            >
              <section className="surface flex h-full min-h-0 flex-col p-3">
                <div className="mb-2 flex items-center justify-between">
                  <div className="text-sm font-semibold">Диалоги</div>
                  <button className="btn px-2 py-1 text-xs" onClick={() => setIsChatListOpen(false)}>
                    Закрыть
                  </button>
                </div>
                {chatListContent}
              </section>
            </div>
          </div>

          <div
            className={`fixed inset-0 z-40 transition-opacity duration-300 xl:hidden ${
              isCompactViewport && isSuggestionsOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
            }`}
          >
            <button className="absolute inset-0 bg-black/40" onClick={() => setIsSuggestionsOpen(false)} aria-label="Закрыть варианты ответа" />
            <div
              className={`absolute right-0 top-0 h-full w-[88vw] max-w-[360px] transform p-2 transition-transform duration-300 ${
                isCompactViewport && isSuggestionsOpen ? 'translate-x-0' : 'translate-x-full'
              }`}
            >
              <aside className="surface h-full min-h-0 overflow-hidden p-2">
                <div className="mb-2 flex items-center justify-between">
                  <div className="text-sm font-semibold">Варианты ответа</div>
                  <button className="btn px-2 py-1 text-xs" onClick={() => setIsSuggestionsOpen(false)}>
                    Закрыть
                  </button>
                </div>
                {suggestionsContent}
              </aside>
            </div>
          </div>
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
                {kbDocs?.map((doc) => (
                  <tr key={doc.id} className="border-t border-[var(--line)]">
                    <td className="px-3 py-2">{doc.source_name}</td>
                    <td className="px-3 py-2">{parseFileExt(doc.source_name)}</td>
                    <td className="px-3 py-2">{doc.source_type}</td>
                    <td className="px-3 py-2">{doc.current_version}</td>
                    <td className="px-3 py-2">{toHumanDate(doc.created_at)}</td>
                    <td className="px-3 py-2">{toHumanDate(doc.deleted_at)}</td>
                    <td className="px-3 py-2">
                      <button
                        className="btn flex gap-1 px-2 py-1 text-xs"
                        onClick={() => onDeleteKbDocument(doc.id)}
                        disabled={Boolean(doc.deleted_at)}
                      >
                        <Trash2 size={13} />
                        Удалить
                      </button>
                    </td>
                  </tr>
                ))}

                {(!kbDocs || kbDocs.length === 0) ? (
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
              disabled={kbPage * KB_PAGE_SIZE >= kbTotal || isKbLoading}
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
              <div className="mb-2 text-sm font-medium">Настройки бэкенда</div>

              <label className="mb-1 block text-xs text-[var(--muted)]">
                Режим по умолчанию для новых тикетов
              </label>
              <select
                className="field"
                value={defaultModeSetting}
                onChange={(event) => setDefaultModeSetting(event.target.value as ChatModeCode)}
              >
                <option value="full_ai">AI ведёт диалог</option>
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
                Эти параметры сохраняются локально и не отправляются в бэкенд.
              </div>
            </div>
          </div>
        </section>
      ) : null}

      {section === 'analytics' ? (
        <section className="surface fade-in-up min-h-[540px] p-3">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-sm font-semibold">Аналитика</div>
              <div className="text-xs text-[var(--muted)]">
                Короткий дашборд по ключевым метрикам
                {analyticsReport ? ` • обновлено ${toHumanDate(analyticsReport.generated_at)}` : ''}
              </div>
            </div>
            <button className="btn btn-primary inline-flex items-center gap-1 text-xs" onClick={() => loadAnalytics(false)}>
              {isAnalyticsLoading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCcw size={13} />}
              Обновить
            </button>
          </div>

          <div className="mb-3 flex flex-wrap items-center gap-2">
            <div className="soft-surface flex items-center gap-1 p-1">
              <button className="btn px-2 py-1 text-xs" onClick={() => onApplyAnalyticsPreset(1)}>
                24ч
              </button>
              <button className="btn px-2 py-1 text-xs" onClick={() => onApplyAnalyticsPreset(7)}>
                7д
              </button>
              <button className="btn px-2 py-1 text-xs" onClick={() => onApplyAnalyticsPreset(30)}>
                30д
              </button>
            </div>

            <button className="btn px-2 py-1 text-xs" onClick={() => setIsAnalyticsRangeOpen((prev) => !prev)}>
              {isAnalyticsRangeOpen ? 'Скрыть даты' : 'Точный период'}
            </button>
          </div>

          {isAnalyticsRangeOpen ? (
            <div className="mb-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-[220px_220px_auto] xl:items-center">
              <input
                type="datetime-local"
                className="field py-2 text-xs"
                value={analyticsFromInput}
                onChange={(event) => setAnalyticsFromInput(event.target.value)}
              />
              <input
                type="datetime-local"
                className="field py-2 text-xs"
                value={analyticsToInput}
                onChange={(event) => setAnalyticsToInput(event.target.value)}
              />
              <button className="btn text-xs" onClick={() => loadAnalytics(false)}>
                Применить период
              </button>
            </div>
          ) : null}

          {analyticsError ? (
            <div className="mb-3 rounded-xl bg-[rgba(209,70,70,0.13)] px-3 py-2 text-sm text-[var(--danger)]">
              {analyticsError}
            </div>
          ) : null}

          {isAnalyticsLoading && !analyticsReport ? (
            <div className="inline-flex items-center gap-2 text-sm text-[var(--muted)]">
              <Loader2 size={14} className="animate-spin" />
              Загружаем отчёт...
            </div>
          ) : null}

          {analyticsReport ? (
            <div className="space-y-3">
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                <AnalyticsKpiCard
                  title="Тикеты за период"
                  value={formatCompactNumber(analyticsReport.tickets.opened_in_period)}
                  hint={`Закрыто: ${formatCompactNumber(analyticsReport.tickets.closed_in_period)}`}
                />
                <AnalyticsKpiCard
                  title="Сообщения за период"
                  value={formatCompactNumber(analyticsReport.messages.in_period)}
                  hint={`Среднее на тикет: ${analyticsReport.messages.avg_per_ticket?.toFixed(1) ?? '—'}`}
                />
                <AnalyticsKpiCard
                  title="AI закрытие"
                  value={formatPercent(analyticsReport.ai_performance.resolution_rate)}
                  hint={`Эскалация: ${formatPercent(analyticsReport.ai_performance.escalation_rate)}`}
                />
                <AnalyticsKpiCard
                  title="Доля попаданий RAG"
                  value={formatPercent(analyticsReport.rag.retrieval.hit_rate)}
                  hint={`Событий: ${formatCompactNumber(analyticsReport.rag.retrieval.events_in_period)}`}
                />
              </div>

              <div className="relative rounded-xl bg-[var(--bg-soft)] p-1">
                <span
                  className="pointer-events-none absolute bottom-1 left-1 top-1 rounded-lg bg-[var(--accent)] shadow-[0_8px_20px_rgba(47,125,244,0.3)] transition-transform duration-300 ease-out"
                  style={{
                    width: `calc((100% - 8px) / ${ANALYTICS_VIEWS.length})`,
                    transform: `translateX(${activeAnalyticsViewIndex * 100}%)`
                  }}
                />
                <div
                  className="relative z-10 grid"
                  style={{ gridTemplateColumns: `repeat(${ANALYTICS_VIEWS.length}, minmax(0, 1fr))` }}
                >
                  {ANALYTICS_VIEWS.map((tab) => (
                    <button
                      key={tab.key}
                      className={`rounded-lg px-2 py-1.5 text-xs font-medium transition-colors duration-200 ${
                        analyticsView === tab.key ? 'text-white' : 'text-[var(--muted)] hover:text-[var(--text)]'
                      }`}
                      onClick={() => setAnalyticsView(tab.key)}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              </div>

              {analyticsView === 'overview' ? (
                <div className="grid gap-3 xl:grid-cols-2">
                  <AnalyticsChartCard title="Статусы тикетов">
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie data={analyticsTicketStatusData} dataKey="value" nameKey="name" innerRadius={58} outerRadius={86}>
                            {analyticsTicketStatusData.map((item, index) => (
                              <Cell key={`ticket-status-${item.name}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                            ))}
                          </Pie>
                          <Tooltip formatter={(value) => formatCompactNumber(Number(value))} />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                  </AnalyticsChartCard>

                  <AnalyticsChartCard title="Кто отправлял сообщения">
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={analyticsMessagesData} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(127,127,127,0.2)" />
                          <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                          <YAxis tick={{ fontSize: 12 }} />
                          <Tooltip formatter={(value) => formatCompactNumber(Number(value))} />
                          <Bar dataKey="value" radius={[8, 8, 0, 0]}>
                            {analyticsMessagesData.map((item, index) => (
                              <Cell key={`messages-${item.name}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </AnalyticsChartCard>

                  <AnalyticsChartCard title="Пользователи за период">
                    <div className="h-56">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={analyticsUserData} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(127,127,127,0.2)" />
                          <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                          <YAxis tick={{ fontSize: 12 }} />
                          <Tooltip formatter={(value) => formatCompactNumber(Number(value))} />
                          <Bar dataKey="value" fill={CHART_COLORS[0]} radius={[8, 8, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </AnalyticsChartCard>

                  <AnalyticsChartCard title="Время решения">
                    <div className="grid grid-cols-3 gap-2 text-xs">
                      <div className="rounded-lg bg-[var(--panel-solid)] p-2">
                        <div className="text-[var(--muted)]">Среднее</div>
                        <div className="mt-1 text-sm font-semibold">
                          {formatDurationShort(analyticsReport.tickets.avg_resolution_time_seconds)}
                        </div>
                      </div>
                      <div className="rounded-lg bg-[var(--panel-solid)] p-2">
                        <div className="text-[var(--muted)]">P50</div>
                        <div className="mt-1 text-sm font-semibold">
                          {formatDurationShort(analyticsReport.tickets.resolution_time_p50_seconds)}
                        </div>
                      </div>
                      <div className="rounded-lg bg-[var(--panel-solid)] p-2">
                        <div className="text-[var(--muted)]">P95</div>
                        <div className="mt-1 text-sm font-semibold">
                          {formatDurationShort(analyticsReport.tickets.resolution_time_p95_seconds)}
                        </div>
                      </div>
                    </div>
                  </AnalyticsChartCard>
                </div>
              ) : null}

              {analyticsView === 'ai' ? (
                <div className="grid gap-3 xl:grid-cols-2">
                  <AnalyticsChartCard title="Эффективность AI" subtitle="Проценты за выбранный период">
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={analyticsAiRatesData} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(127,127,127,0.2)" />
                          <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                          <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 12 }} />
                          <Tooltip formatter={(value) => `${Number(value)}%`} />
                          <Bar dataKey="value" radius={[8, 8, 0, 0]} fill={CHART_COLORS[1]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </AnalyticsChartCard>

                  <AnalyticsChartCard title="Распределение режимов чатов">
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie data={analyticsModeData} dataKey="value" nameKey="name" innerRadius={56} outerRadius={86}>
                            {analyticsModeData.map((item, index) => (
                              <Cell key={`mode-${item.name}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                            ))}
                          </Pie>
                          <Tooltip formatter={(value) => formatCompactNumber(Number(value))} />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                  </AnalyticsChartCard>

                  <AnalyticsChartCard title="Ключевые AI метрики">
                    <div className="grid gap-2 sm:grid-cols-3">
                      <AnalyticsKpiCard
                        title="Закрыто AI"
                        value={formatCompactNumber(analyticsReport.ai_performance.tickets_closed_by_ai)}
                      />
                      <AnalyticsKpiCard
                        title="Эскалаций"
                        value={formatCompactNumber(analyticsReport.ai_performance.tickets_escalated_to_human)}
                      />
                      <AnalyticsKpiCard
                        title="Сообщений до эскалации"
                        value={analyticsReport.ai_performance.avg_messages_before_escalation?.toFixed(1) ?? '—'}
                      />
                    </div>
                  </AnalyticsChartCard>
                </div>
              ) : null}

              {analyticsView === 'knowledge' ? (
                <div className="grid gap-3 xl:grid-cols-2">
                  <AnalyticsChartCard title="Обработка документов">
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={analyticsIngestionData} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(127,127,127,0.2)" />
                          <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                          <YAxis tick={{ fontSize: 12 }} />
                          <Tooltip formatter={(value) => formatCompactNumber(Number(value))} />
                          <Bar dataKey="value" radius={[8, 8, 0, 0]}>
                            {analyticsIngestionData.map((item, index) => (
                              <Cell key={`ingestion-${item.name}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </AnalyticsChartCard>

                  <AnalyticsChartCard title="Состояние RAG">
                    <div className="grid gap-2 sm:grid-cols-2">
                      <AnalyticsKpiCard title="Документов" value={formatCompactNumber(analyticsReport.rag.total_documents)} />
                      <AnalyticsKpiCard title="Активных документов" value={formatCompactNumber(analyticsReport.rag.active_documents)} />
                      <AnalyticsKpiCard title="Активных чанков" value={formatCompactNumber(analyticsReport.rag.total_chunks)} />
                      <AnalyticsKpiCard
                        title="Средний score"
                        value={analyticsReport.rag.retrieval.avg_score?.toFixed(2) ?? '—'}
                      />
                    </div>
                  </AnalyticsChartCard>
                </div>
              ) : null}
            </div>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
