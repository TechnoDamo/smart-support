# Smart Support Frontend

Next.js фронтенд для operator workspace (`Inbox`, `Knowledge Base`, `Settings`) с прямым подключением к backend API.

## Запуск

```bash
nvm use
npm install
npm run dev
```

Рекомендуемая версия Node.js: `22.x` LTS.
`Next 14.2.x` в этом проекте может падать на `Node 25` внутри dev-server ещё до выполнения кода приложения.

API base URL настраивается через `NEXT_PUBLIC_SUPPORT_API_BASE_URL`.

Для текущего backend из этого репозитория дефолтный адрес такой:

```bash
NEXT_PUBLIC_SUPPORT_API_BASE_URL=http://127.0.0.1:8081
```
