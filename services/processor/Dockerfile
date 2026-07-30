FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Установка системных библиотек
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir --default-timeout=1000 torch torchvision torchaudio

RUN pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

COPY . .

CMD ["python", "main.py"]