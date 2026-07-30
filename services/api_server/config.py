from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Мы объявляем переменные без дефолтных значений.
    # Это значит, что если их не будет в .env или переменных окружения.
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    
    # Здесь дефолтное значение допустимо, так как это внутреннее имя сервиса в Docker
    DB_HOST: str = "db" 
    DB_PORT: str = "5432"

    # Эти настройки нужны для Pydantic, чтобы он знал, откуда читать,
    # если мы запускаем код локально (не в Докере)
    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

# Создаем единственный экземпляр настроек
settings = Settings()