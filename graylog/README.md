# Graylog: централизованное логирование

Этот модуль поднимает Graylog 5.2 + Elasticsearch 7.17 + MongoDB 6 и автоматически создаёт GELF TCP input, в который backend Smart Support шлёт структурированные JSON-логи.

## Быстрый старт

1. **Поднять стек вместе с Graylog:**

   ```bash
   cd /Users/damir/Desktop/smart-support
   make up AI=cloud STORAGE=minio GRAYLOG=true
   ```

   `make` автоматически:
   - добавляет профиль `graylog` в docker-compose;
   - прокидывает в backend переменные `GRAYLOG_ENABLED=true`, `GRAYLOG_HOST=graylog`, `GRAYLOG_PORT=12201`, `GRAYLOG_PROTOCOL=tcp`;
   - запускает одноразовый контейнер `smart-support-graylog-init`, который создаёт GELF input через REST API (`POST /api/system/inputs`).

2. **Открыть веб-интерфейс:**

   - URL: <http://localhost:19000>
   - Логин: `admin`
   - Пароль: `admin` (меняется через `GRAYLOG_ADMIN_PASSWORD` в `.env`)

3. **Проверить, что input создан:**

   - `System → Inputs`
   - В списке должен быть `Smart Support Backend GELF TCP` на порту `12201`.
   - Если его нет — проверьте логи `docker logs smart-support-graylog-init`.

## Конфигурация логирования

Backend использует `python-json-logger` и собственный GELF-хендлер. Параметры — в общем `.env` в корне репозитория:

```bash
# Graylog Configuration
GRAYLOG_ENABLED=false
GRAYLOG_HOST=graylog          # внутри docker-стека; для локального backend — localhost
GRAYLOG_PORT=12201
GRAYLOG_PROTOCOL=tcp          # tcp или udp
GRAYLOG_ADMIN_PASSWORD=admin  # читается init-контейнером

LOG_LEVEL=INFO
LOG_FORMAT=json               # json включает GELF-поля, text — удобно в консоли
```

Важные нюансы:

- `GRAYLOG_ENABLED` выставляется автоматически при `make up ... GRAYLOG=true` — вручную включать не нужно.
- `GRAYLOG_HOST=graylog` работает только в docker-стеке (по имени сервиса). Если backend стартует локально вне Docker — замените на `localhost`.
- `GRAYLOG_ADMIN_PASSWORD` читается init-сервисом и должен совпадать с хешем `GRAYLOG_ROOT_PASSWORD_SHA2` в `graylog/docker-compose.yml`. Для дефолтного `admin` хеш уже зашит.

## Какие поля попадают в лог

Каждая запись включает:

- `timestamp` — ISO 8601;
- `level` — `DEBUG | INFO | WARNING | ERROR | CRITICAL`;
- `logger` — имя модуля;
- `message` — текст сообщения;
- `service` — `smart-support-backend`;
- `environment` — `dev | prod | test`;
- `request_id` — ID HTTP-запроса (из middleware);
- `user_id` — ID авторизованного пользователя, если есть;
- `endpoint`, `method`, `status_code`, `duration_ms` — для HTTP-запросов;
- `db_operation`, `db_table`, `db_duration_ms` — для SQL-запросов;
- `error_type`, `stack_trace` — для исключений.

Дополнительные kwargs, переданные через `logger.info("msg", extra={...})`, тоже попадают в GELF в виде отдельных полей.

## Безопасность

1. **Маскирование чувствительных данных.** Пароли, токены, API-ключи маскируются в middleware до отправки в лог. Тела запросов/ответов очищаются от персональных данных.
2. **Прод.** Обязательно:
   - смените `GRAYLOG_ADMIN_PASSWORD` и перегенерируйте `GRAYLOG_ROOT_PASSWORD_SHA2`;
   - закройте порт 19000 файрволом / проксируйте через ingress c TLS;
   - настройте retention policies для Elasticsearch (`System → Indices`).

## Устранение неполадок

**Graylog не стартует**
- `docker compose -f docker-compose.yml --profile graylog logs graylog`
- Проверьте, что порты `19000`, `12201`, `5555`, `1514` свободны.
- Elasticsearch требует минимум 512 МБ heap; при нехватке памяти контейнер падает с OOM.

**Логи не появляются**
- Убедитесь, что `smart-support-graylog-init` завершился с кодом 0:
  ```bash
  docker logs smart-support-graylog-init
  ```
- Проверьте, что в Graylog UI есть input `Smart Support Backend GELF TCP`.
- Проверьте backend-логи на ошибки подключения к Graylog.
- Внутри Docker-стека backend должен писать по хосту `graylog`, не `localhost`.

**Много дисковой записи / распухает `elasticsearch_data/`**
- Настройте retention: `System → Indices → Default index set → Rotation / Retention`.
- Уменьшите `ES_JAVA_OPTS` и размер шардов под dev-нагрузку.

## Интеграция с backend

- `python-json-logger` → структурированный JSON.
- Собственный GELF-хендлер шлёт по TCP/UDP с автоматическим chunking больших сообщений.
- FastAPI middleware добавляет `request_id`, тайминги, `user_id`.
- SQLAlchemy events логируют медленные запросы (`db_operation`, `db_duration_ms`).

## Готовые запросы и дашборды

В Graylog UI полезно сохранить:

- `service:"smart-support-backend" AND level:ERROR` — все ошибки backend.
- `service:"smart-support-backend" AND duration_ms:>1000` — медленные HTTP-запросы.
- `logger:"app.services.ai_orchestrator"` — цепочка работы AI-оркестратора.
- `db_duration_ms:>500` — медленные SQL-запросы.
