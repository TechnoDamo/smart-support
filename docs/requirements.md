# Smart Support — Системные требования и описание алгоритмов

> Версия: MVP (однотенантная, без аутентификации)  
> Язык реализации бэкенда: Python / FastAPI  
> Язык реализации фронтенда: TypeScript / Next.js  
> БД: PostgreSQL + Qdrant (векторная)

---

## 1. Обзор системы

Smart Support — платформа поддержки пользователей с интегрированным AI-оператором. Система принимает сообщения из внешних каналов (Telegram, в будущем — другие), обрабатывает их через AI-оркестратор и/или операторов-людей, ведёт базу знаний (RAG) и предоставляет аналитику.

Ключевые сущности:
- **Чат (Chat)** — сессия пользователя в конкретном канале (один пользователь, один канал).
- **Тикет (Ticket)** — конкретный запрос/обращение внутри чата. В чате тикеты идут последовательно: не более одного активного тикета одновременно.
- **Сообщение (Message)** — единица обмена внутри тикета. Имеет отправителя: `user`, `ai_operator`, `operator`.
- **Режим чата (Chat Mode)** — определяет, кто обрабатывает входящие сообщения.
- **Статус тикета (Ticket Status)** — текущее состояние тикета в его жизненном цикле.

---

## 2. Режимы чата

| Код | Название | Поведение |
|-----|----------|-----------|
| `full_ai` | Полный AI | Все входящие сообщения обрабатывает AI-оркестратор. Человек подключается только при явной просьбе пользователя или при недостаточной уверенности AI. |
| `ai_assist` | AI-ассистент | Сообщения видит оператор-человек. AI предоставляет подсказки с контекстом из RAG по запросу оператора. |
| `no_ai` | Без AI | Все сообщения идут напрямую операторам-людям. AI не участвует. |

Режим хранится на уровне **чата** и может быть изменён оператором в любой момент. При создании нового чата используется значение по умолчанию из конфигурации (`DEFAULT_CHAT_MODE`).

---

## 3. Статусы тикета

| Код | Название | Смысл |
|-----|----------|-------|
| `pending_ai` | Ожидает AI | Тикет ждёт ответа AI-оператора. |
| `pending_human` | Ожидает оператора | Тикет передан человеку и ожидает его ответа. |
| `pending_user` | Ожидает пользователя | Ответ (AI или оператор) отправлен, система ждёт реакции пользователя. |
| `closed` | Закрыт | Тикет завершён (вручную или по таймауту бездействия). |

### Диаграмма переходов статусов

```
[Создание тикета]
       │
       ▼
  pending_ai  ──(режим no_ai)──►  pending_human
       │                               │
       │ AI ответил                    │ Оператор ответил
       ▼                               ▼
  pending_user  ◄──────────────  pending_user
       │
       │ Пользователь ответил
       ├──(full_ai / ai_assist)──►  pending_ai
       ├──(no_ai)────────────────►  pending_human
       │
       │ Таймаут бездействия (планировщик)
       ▼
    closed
       ▲
       │ Ручное закрытие (оператор) — TODO
```

Переход `pending_ai → pending_human` происходит при эскалации AI-оркестратором (см. раздел 6).  
Переход `pending_human → pending_ai` не предусмотрен (режим `no_ai` → ответ только от людей).

---

## 4. Жизненный цикл тикета

### 4.1 Создание тикета

Тикет создаётся автоматически при получении первого сообщения от пользователя в чате, если у чата нет активного тикета.

**Алгоритм:**
1. Входящее сообщение привязывается к чату.
2. Проверяется наличие активного тикета (`status IN (pending_ai, pending_human, pending_user)`).
3. Если активного тикета нет — создаётся новый:
   - `title` = `"Тикет {ticket_id}"` (по умолчанию)
   - `status` определяется режимом чата:
     - `no_ai` → `pending_human`
     - `full_ai` / `ai_assist` → `pending_ai`
4. Сообщение пользователя сохраняется в `messages` с `entity = user`.
5. Записывается событие `ticket_status_events` (from=null, to=начальный статус).

### 4.2 Обработка входящего сообщения

После сохранения сообщения и определения статуса тикета:

- Если статус стал `pending_ai` → передать в AI-оркестратор (асинхронно).
- Если статус `pending_human` → уведомить операторов (push в UI через polling).
- Если тикет был `pending_user` → сменить статус:
  - `full_ai` / `ai_assist` → `pending_ai`
  - `no_ai` → `pending_human`

### 4.3 Закрытие тикета

Тикет закрывается планировщиком автоматически, если:
- Статус = `pending_user`
- Время последнего сообщения превышает `TICKET_INACTIVITY_TIMEOUT_MINUTES` (из конфига)

При закрытии:
1. Планировщик выбирает просроченные тикеты.
2. Для каждого тикета вызывается LLM для генерации `summary` на основе истории сообщений тикета.
3. Поле `summary` и `time_closed` обновляются.
4. Статус меняется на `closed`.
5. Записывается `ticket_status_events` (changed_by=`ai_operator`, reason="auto_close_inactivity").

---

## 5. AI-оркестратор

AI-оркестратор — компонент бэкенда, принимающий решение об обработке тикета в режиме `full_ai`. Действует как HTTP-клиент к собственному API системы (от имени сущности `ai_operator`).

### 5.1 Входные условия запуска

Оркестратор запускается, когда тикет переходит в статус `pending_ai`.

### 5.2 Алгоритм обработки (full_ai)

```
1. Получить историю сообщений тикета
2. Получить последнее сообщение пользователя
3. Вызвать RAG-пайплайн:
   - embedding(последнее сообщение пользователя) → запрос в Qdrant
   - Получить top-k релевантных чанков
   - Сохранить rag_retrieval_event + rag_retrieval_results
4. Сформировать запрос к LLM:
   - system prompt (из файла prompts/ai_operator.txt)
   - контекст из RAG-чанков
   - история переписки тикета
   - последнее сообщение пользователя
5. Получить ответ LLM в структурированном формате (см. 5.3)
6. Обработать действие:
   - action = "reply"       → отправить ответ, тикет → pending_user
   - action = "escalate"    → отправить сообщение об эскалации, тикет → pending_human
```

### 5.3 Формат ответа LLM

LLM обязан вернуть JSON следующей структуры (инструкция задана в system prompt):

```json
{
  "action": "reply" | "escalate",
  "response_text": "Текст ответа пользователю",
  "escalation_reason": "Причина эскалации (только при action=escalate)"
}
```

Примеры триггеров эскалации (описаны в system prompt):
- Пользователь явно просит соединить с оператором / живым человеком.
- Контекст из RAG недостаточен для уверенного ответа (LLM не знает ответа).

При `action = "escalate"`:
- Отправляется `response_text` пользователю (например: "Передаю вас оператору, ожидайте.").
- Статус тикета меняется на `pending_human`.
- Режим чата **не меняется** (остаётся `full_ai` — следующий тикет снова пойдёт в AI).
- Записывается `ticket_status_events` (changed_by=`ai_operator`, reason=`escalation_reason`).

При `action = "reply"`:
- Отправляется `response_text` пользователю.
- Статус тикета меняется на `pending_user`.
- Чанки, использованные в ответе, помечаются `used_in_answer = true` в `rag_retrieval_results`.

### 5.4 Режим ai_assist

В режиме `ai_assist` AI-оркестратор **не отвечает автоматически**. Вместо этого:
- RAG-пайплайн запускается только по явному запросу оператора (`POST /chats/{chat_id}/suggestions`).
- Оператор получает до `max_suggestions` (по умолчанию 3) вариантов ответа с цитатами.
- Оператор выбирает или редактирует предложение и отправляет вручную.

---

## 6. RAG-пайплайн

### 6.1 Загрузка документов (Ingestion)

```
Оператор загружает файл
       │
       ▼
POST /rag/documents (multipart)
       │
       ▼
1. Создать rag_document (source_type, source_name, mime_type, storage_url)
2. Создать rag_ingestion_job (operation=upsert_document, status=queued)
3. Вернуть {document_id, ingestion_job_id, status=queued}
       │
       ▼ (асинхронно — воркер)
4. Статус job → processing
5. Создать rag_document_version (extraction_status=processing)
6. Извлечь текст из файла (OCR / парсинг по mime_type)
7. content_hash = SHA256(extracted_text)
8. Разбить на чанки (по токенам, с overlap)
9. Для каждого чанка:
   a. Создать rag_document_chunk (chunk_index, chunk_text, chunk_token_count)
   b. Получить embedding от провайдера
   c. Сохранить вектор в Qdrant (qdrant_point_id)
10. Обновить extraction_status = ready
11. Обновить rag_document.current_version
12. Статус job → done
    (при ошибке → failed + error_message)
```

### 6.2 Удаление документов

```
DELETE /rag/documents/{document_id}
       │
       ▼
1. Мягкое удаление: rag_document.deleted_at = now()
2. Создать rag_ingestion_job (operation=delete_document, status=queued)
       │
       ▼ (асинхронно — воркер)
3. Удалить точки из Qdrant по qdrant_point_id чанков документа
4. Мягкое удаление чанков: rag_document_chunks.deleted_at = now()
5. Статус job → done
```

### 6.3 Retrieval (поиск)

```
Входной текст (запрос пользователя или draft оператора)
       │
       ▼
1. Получить embedding от провайдера
2. Запрос в Qdrant: top_k=N, min_score=threshold (из конфига)
3. Сохранить rag_retrieval_event (query_text, top_k, min_score, chat_id, ticket_id, message_id)
4. Для каждого результата сохранить rag_retrieval_result (chunk_id, rank, score, used_in_answer=false)
5. Вернуть список чанков с их текстом и score
```

---

## 7. Модуль Outbox (исходящие сообщения)

Реализует паттерн Transactional Outbox для гарантированной доставки сообщений в каналы.

**Алгоритм отправки:**
1. Сообщение сначала сохраняется в `messages` (БД) — это атомарная операция вместе с изменением статуса тикета.
2. Одновременно создаётся запись в `outbox` (таблица не показана в схеме — требует добавления): `{message_id, channel, status=pending, attempts=0}`.
3. Планировщик периодически выбирает `outbox` записи со статусом `pending` или `retry`.
4. Отправляет в канал (Telegram API и т.д.).
5. При успехе: `outbox.status = sent`.
6. При ошибке: `attempts += 1`. Если `attempts < OUTBOX_MAX_RETRIES` → `status = retry`. Иначе → `status = failed`.

Количество попыток и интервал между ними управляются конфигурационными переменными (`OUTBOX_MAX_RETRIES`, `OUTBOX_RETRY_INTERVAL_SECONDS`).

---

## 8. Планировщик (Scheduler)

Запускает периодические задачи по расписанию (cron-интервалы из конфига).

### 8.1 Автозакрытие тикетов

**Расписание:** каждые `SCHEDULER_TICKET_CLOSE_CHECK_INTERVAL_MINUTES` минут.

**Алгоритм:**
```sql
SELECT t.id FROM tickets t
JOIN messages m ON m.ticket_id = t.id
WHERE t.status_id = (SELECT id FROM ticket_statuses WHERE code = 'pending_user')
  AND m.time = (SELECT MAX(time) FROM messages WHERE ticket_id = t.id)
  AND m.time < NOW() - INTERVAL '{TICKET_INACTIVITY_TIMEOUT_MINUTES} minutes'
```
Для каждого найденного тикета:
1. Загрузить историю сообщений.
2. Вызвать LLM с промптом `prompts/ticket_summary.txt` → получить `summary`.
3. Обновить `tickets.summary`, `tickets.time_closed = NOW()`.
4. Сменить статус на `closed`, записать `ticket_status_events`.

### 8.2 Повтор задач Outbox

**Расписание:** каждые `OUTBOX_RETRY_INTERVAL_SECONDS` секунд.

Выбирает записи `outbox` со статусом `retry` и `next_attempt_at <= NOW()`, пытается повторить отправку.

### 8.3 Повтор неудачных задач Ingestion

**Расписание:** каждые `SCHEDULER_INGESTION_RETRY_INTERVAL_MINUTES` минут.

Выбирает `rag_ingestion_jobs` со статусом `failed` (до `RAG_INGESTION_MAX_RETRIES` попыток) и ставит их в очередь повторно (`status = queued`).

---

## 9. Системные промпты

Системные промпты хранятся в виде `.txt`-файлов в директории `prompts/` корня бэкенда. При старте сервиса промпты загружаются в память.

| Файл | Используется | Описание |
|------|-------------|----------|
| `prompts/ai_operator.txt` | AI-оркестратор (full_ai) | Инструктирует LLM отвечать на вопросы по теме поддержки, использовать предоставленный RAG-контекст, эскалировать при явной просьбе о человеке или при недостатке контекста. Задаёт формат ответа в JSON `{action, response_text, escalation_reason}`. |
| `prompts/ticket_summary.txt` | Планировщик (автозакрытие) | Инструктирует LLM сформировать краткое резюме завершённого диалога. Вход: история сообщений тикета. Выход: текстовое резюме (1–3 предложения). |
| `prompts/suggestions.txt` | RAG suggestions (ai_assist) | Инструктирует LLM сформировать N вариантов ответа оператора на основе RAG-контекста и истории переписки. |

### Пример инструкции в `prompts/ai_operator.txt`

```
Ты — AI-оператор службы поддержки. Отвечай строго по теме обращений пользователей.
Используй предоставленный контекст из базы знаний для формирования точных ответов.

Правила эскалации:
- Если пользователь явно просит соединить с оператором/живым человеком — эскалируй.
- Если предоставленного контекста недостаточно для уверенного ответа — эскалируй.
- В остальных случаях — отвечай самостоятельно.

Ты ВСЕГДА должен возвращать ответ строго в формате JSON:
{
  "action": "reply" | "escalate",
  "response_text": "<текст ответа пользователю>",
  "escalation_reason": "<причина (только при action=escalate)>"
}

Не добавляй ничего вне JSON.
```

---

## 10. Модель данных

Полная схема — файл `db/schema.dbml`. Ниже описаны ключевые изменения и бизнес-правила.

### Статусы тикетов (справочник `ticket_statuses`)

| code | Описание |
|------|----------|
| `pending_ai` | Ожидает ответа AI |
| `pending_human` | Ожидает ответа оператора-человека |
| `pending_user` | Ожидает ответа пользователя (ответ отправлен, таймер бездействия запущен) |
| `closed` | Закрыт |

### Бизнес-правила БД

1. **Один активный тикет на чат:** частичный уникальный индекс по `(chat_id) WHERE status IN ('pending_ai','pending_human','pending_user')`.
2. **Порядок сообщений:** поле `seq` уникально в рамках чата (`UNIQUE (chat_id, seq)`).
3. **Мягкое удаление документов:** `rag_documents.deleted_at IS NOT NULL` означает удалён.
4. **Версионирование документов:** `rag_documents.current_version` указывает на активную версию.

### Таблица outbox (добавить в схему)

```dbml
Table "public"."outbox_messages" {
  "id"             uuid         [pk, not null]
  "message_id"     uuid         [not null, ref: > "public"."messages"."id"]
  "channel_code"   varchar(32)  [not null]
  "payload"        jsonb        [not null, note: 'Channel-specific send payload']
  "status"         varchar(32)  [not null, note: 'pending | retry | sent | failed']
  "attempts"       int          [not null, default: 0]
  "next_attempt_at" timestamptz
  "error_message"  text
  "created_at"     timestamptz  [not null, default: `now()`]
  "sent_at"        timestamptz

  Indexes {
    (status, next_attempt_at) [name: "idx_outbox_messages_status_next_attempt"]
    message_id                [name: "idx_outbox_messages_message_id"]
  }
}
```

---

## 11. API

Полная спецификация — файл `docs/openapi.yaml`. Base URL: `http://127.0.0.1:8081/api/v1`.

### Группы эндпоинтов

| Тег | Эндпоинты |
|-----|-----------|
| **Тикеты** | `GET /tickets`, `GET /tickets/{id}`, `PATCH /tickets/{id}` |
| **Чаты** | `GET /chats`, `GET /chats/{id}`, `POST /chats/{id}/mode` |
| **Сообщения** | `POST /chats/{id}/messages` |
| **Подсказки** | `POST /chats/{id}/suggestions` |
| **Настройки** | `PUT /settings/default-new-ticket-mode` |
| **RAG** | `GET /rag/documents`, `POST /rag/documents`, `DELETE /rag/documents/{id}` |
| **Аналитика** | `GET /analytics/report` |

### Примечания по реализации

- `POST /chats/{id}/messages` — используется как операторами-людьми (через UI), так и AI-оркестратором (HTTP-клиент от имени `ai_operator`). Поле `entity` в сохранённом сообщении определяется по тому, кто вызвал эндпоинт (логика на бэкенде).
- `POST /chats/{id}/suggestions` — запускает RAG retrieval + LLM через промпт `prompts/suggestions.txt`. Возвращает до `max_suggestions` вариантов с цитатами.
- `GET /analytics/report` — агрегирует данные из PostgreSQL за указанный период (`?from=` / `?to=`). По умолчанию — последние 7 дней.

---

## 12. Конфигурация

Все параметры передаются через переменные окружения.

| Переменная | Тип | Описание |
|-----------|-----|----------|
| `DATABASE_URL` | string | PostgreSQL DSN |
| `QDRANT_URL` | string | URL Qdrant |
| `LLM_PROVIDER_URL` | string | URL LLM-провайдера |
| `LLM_MODEL` | string | Название модели LLM |
| `EMBEDDING_PROVIDER_URL` | string | URL провайдера эмбеддингов |
| `EMBEDDING_MODEL` | string | Название embedding-модели |
| `OBJECT_STORAGE_URL` | string | URL объектного хранилища |
| `DEFAULT_CHAT_MODE` | enum | Режим чата по умолчанию (`full_ai` / `ai_assist` / `no_ai`) |
| `TICKET_INACTIVITY_TIMEOUT_MINUTES` | int | Таймаут бездействия перед автозакрытием тикета |
| `OUTBOX_MAX_RETRIES` | int | Макс. число попыток доставки исходящего сообщения |
| `OUTBOX_RETRY_INTERVAL_SECONDS` | int | Интервал между попытками Outbox |
| `RAG_RETRIEVAL_TOP_K` | int | Количество чанков, возвращаемых RAG |
| `RAG_RETRIEVAL_MIN_SCORE` | float | Минимальный score релевантности (0–1) |
| `RAG_INGESTION_MAX_RETRIES` | int | Макс. число повторных попыток для failed-задач Ingestion |
| `SCHEDULER_TICKET_CLOSE_CHECK_INTERVAL_MINUTES` | int | Интервал проверки тикетов на автозакрытие |
| `SCHEDULER_INGESTION_RETRY_INTERVAL_MINUTES` | int | Интервал повтора failed Ingestion jobs |

---

## 13. Фронтенд (Operator UI)

Технологический стек: Next.js 14, TypeScript, Tailwind CSS.  
URL среды: `http://127.0.0.1:3000`  
Конфигурация: `NEXT_PUBLIC_SUPPORT_API_BASE_URL` (по умолчанию `http://127.0.0.1:8081/api/v1`)

### Ключевые экраны

| Экран | Назначение |
|-------|-----------|
| **Inbox** | Список тикетов (фильтрация по статусу, поиск), детальная карточка с историей переписки, смена режима чата, отправка сообщений, запрос AI-подсказок |
| **Knowledge Base** | Загрузка/удаление документов базы знаний, отслеживание статуса ingestion |
| **Settings** | Установка режима по умолчанию для новых тикетов |

### Поведение фронтенда

- **Polling:** каждые 4 секунды тихо обновляет список тикетов и карточку активного тикета.
- **Оптимистичный UI:** события режима/статуса добавляются локально сразу, без ожидания следующего poll-цикла.
- **URL-состояние:** секция, вкладка, фильтры, страница и поиск сохраняются в query string (bookmarkable).
- **Mock API:** встроенный mock с авто-генерацией входящих сообщений каждые 12 секунд — для разработки без бэкенда.

---

## 14. Структура директорий бэкенда (рекомендуемая)

```
backend/
├── prompts/
│   ├── ai_operator.txt       # System prompt для AI-оркестратора
│   ├── ticket_summary.txt    # System prompt для генерации summary
│   └── suggestions.txt       # System prompt для генерации подсказок
├── app/
│   ├── api/                  # FastAPI роутеры
│   ├── modules/
│   │   ├── product/          # Логика чатов/тикетов/сообщений
│   │   ├── ai_orchestrator/  # AI-оркестратор
│   │   ├── rag/              # RAG ingestion + retrieval
│   │   ├── outbox/           # Outbox модуль
│   │   ├── analytics/        # Аналитика
│   │   └── scheduler/        # Планировщик
│   ├── adapters/
│   │   ├── telegram/         # Telegram webhook/polling адаптор
│   │   └── ...               # Будущие адапторы
│   └── config.py             # Конфигурация из env
└── db/
    └── schema.dbml
```
