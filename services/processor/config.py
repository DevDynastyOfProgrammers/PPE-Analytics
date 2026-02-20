# processor/config.py

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # RabbitMQ
    RABBITMQ_HOST: str = "rabbitmq"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "guest"
    RABBITMQ_PASS: str = "guest"
    QUEUE_NAME_FRAMES: str = "raw_frames_queue"
    QUEUE_NAME_ALERTS: str = "violation_alerts_queue"

    # Database / API (чтобы загружать зоны)
    API_SERVER_URL: str = "http://api_server:8000"

    QUEUE_NAME_STREAM: str = "processed_stream_queue"

    # Model Configuration
    # "MOCK" - для тестов без GPU и моделей, "TRITON" - для боевого режима
    DETECTION_MODE: str = "MOCK" 
    TRITON_URL: str = "triton:8000"

    class Config:
        env_file = ".env"

settings = Settings()