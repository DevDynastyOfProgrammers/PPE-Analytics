FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV OPENCV_VIDEOIO_DEBUG=1

WORKDIR /app

# 1. Установка системных зависимостей (FFmpeg и OpenCV)
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-opencv \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# 2. Python зависимости
COPY requirements.txt .
RUN sed -i '/opencv/d' requirements.txt && \
    pip3 install --no-cache-dir -r requirements.txt

# 3. Копируем код приложения
COPY . .  

CMD ["python3", "main.py"]