from pydantic_settings import BaseSettings, SettingsConfigDict


class ClientSettings(BaseSettings):
    """Настройки подключения desktop-клиента к сервисам PPE Analytics."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    CLIENT_API_HOST: str = "localhost"
    API_SERVER_PORT: int = 8888
    CLIENT_RABBITMQ_HOST: str = "localhost"
    CLIENT_RABBITMQ_PORT: int = 5672
    RABBITMQ_DEFAULT_USER: str = "guest"
    RABBITMQ_DEFAULT_PASS: str = "guest"


settings = ClientSettings()