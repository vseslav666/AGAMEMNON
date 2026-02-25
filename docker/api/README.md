tacacs-api/
├── app/
│   ├── __init__.py
│   ├── main.py                # Основной файл приложения FastAPI
│   ├── models.py              # Модели Pydantic
│   ├── database.py            # Настройка подключения к БД
│   ├── tacacs_db.py           # Скрипт работы tacacs с БД 
│   └── repositories/
│       ├── __init__.py
│       └── user_repository.py # Репозиторий для работы с пользователями
├── requirements.txt           # Зависимости Python
├── Dockerfile                # Docker образ приложения
├── docker-compose.yml        # Docker Compose для запуска всего стека
└── README.md                 # Документация проекта

## Доступ к API через reverse proxy

Для стабильного доступа с других ПК API рекомендуется публиковать не напрямую, а через proxy.

- Внешний адрес UI: `https://<SERVER_IP>/`
- Внешний адрес API для браузера: `https://<SERVER_IP>/api/*`
- Внутренний upstream API: `tacacs-api:8000`

Маршрутизация задаётся в [`docker/nginx/default.conf`](docker/nginx/default.conf),
а запуск сервисов — в [`docker/docker-compose.yml`](docker/docker-compose.yml).

### TLS сертификат

- Для `nginx` используется единый PEM-файл: [`docker/nginx/certs/tls.pem`](docker/nginx/certs/tls.pem)
- PEM должен содержать:
  - блок `-----BEGIN CERTIFICATE-----`
  - блок `-----BEGIN PRIVATE KEY-----` (или эквивалент приватного ключа)
