FROM python:3.9-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копирование файлов зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY . .

# Создание необходимых директорий
RUN mkdir -p scripts logs

# Предполагаем, что скрипт totp.py будет добавлен в папку scripts
# Если его нет, создадим заглушку для тестирования
RUN if [ ! -f scripts/totp.py ]; then \
        echo "print('TOTP script placeholder')" > scripts/totp.py; \
    fi


# Запуск приложения
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
