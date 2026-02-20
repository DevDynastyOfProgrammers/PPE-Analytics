# ingestor/config.py

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # БД (для чтения списка камер)
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DB_HOST: str = "db"
    DB_PORT: str = "5432"

    # RabbitMQ (куда слать кадры)
    RABBITMQ_HOST: str = "rabbitmq"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "guest"
    RABBITMQ_PASS: str = "guest"
    QUEUE_NAME_FRAMES: str = "raw_frames_queue"

    # Настройки захвата
    FPS_LIMIT: int = 5 # Отправляем не более 5 кадров в секунду (экономия ресурсов)
    FRAME_WIDTH: int = 640 # Ресайз перед отправкой

    class Config:
        env_file = ".env"

settings = Settings()