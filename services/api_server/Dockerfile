# api_server/Dockerfile
# 1. Используем официальный образ Python
FROM python:3.10-slim

# 2. Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# 3. Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Копируем исходный код нашего сервиса
COPY . .

# 5. Команда, которая будет выполняться при запуске контейнера
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]