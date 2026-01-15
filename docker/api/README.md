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
