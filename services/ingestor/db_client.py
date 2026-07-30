from sqlalchemy import create_engine, text
from config import settings


def get_db_url():
    return (
        f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.POSTGRES_DB}"
    )


engine = create_engine(get_db_url(), pool_pre_ping=True)


def get_active_cameras():
    """Возвращает список активных камер в формате id и rtsp_url."""
    cameras = []

    try:
        with engine.connect() as connection:
            result = connection.execute(
                text("SELECT id, rtsp_url FROM cameras WHERE is_active = true")
            )
            cameras = [{"id": row.id, "rtsp_url": row.rtsp_url} for row in result]
    except Exception as error:
        print(f"❌ Ошибка чтения БД: {error}")

    return cameras