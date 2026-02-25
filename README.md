
## Архитектура проекта

### Общая схема системы
![Architecture Diagram](docs/images/architecture/architecture.svg)

### Взаимодействие модулей
![Module Interaction](docs/images/architecture/interaction.svg)

## Структура проекта в виде диаграммы
![Project Structure](docs/images/architecture/project_strucrure.svg) 

## Запуск через reverse proxy (HTTPS 443)

Для доступа с других компьютеров без ребилда фронтенда используется [`docker/docker-compose.yml`](docker/docker-compose.yml).

- Внешняя точка входа: `https://<SERVER_IP>/`
- UI проксируется на [`tacacs-frontend:3000`](docker/docker-compose.yml)
- API проксируется по пути `https://<SERVER_IP>/api/*` на [`tacacs-api:8000`](docker/docker-compose.yml)

Ключевые файлы:

- [`docker/nginx/default.conf`](docker/nginx/default.conf) — правила reverse proxy (`/` и `/api/`) + TLS
- [`frontend/src/lib/api/client.ts`](frontend/src/lib/api/client.ts:24) — базовый URL API по умолчанию `"/api"`
- [`docker/nginx/certs/tls.pem`](docker/nginx/certs/tls.pem) — корпоративный PEM (сертификат + приватный ключ)

### Как запустить

1. Поднять стек:

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

2. Подготовить сертификат:

- положить PEM-файл в [`docker/nginx/certs/tls.pem`](docker/nginx/certs/tls.pem)
- PEM должен содержать и `BEGIN CERTIFICATE`, и `BEGIN PRIVATE KEY`

3. Открыть с клиентского ПК:

- `https://<SERVER_IP>/`

4. Проверить в DevTools, что запросы идут на относительный путь `/api/...`.

### Примечание

При смене IP/домена сервера ребилд фронтенда не требуется: браузер обращается к тому же origin, а маршрутизация в API выполняется proxy.
