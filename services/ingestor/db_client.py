from sqlalchemy import create_engine, text
from config import settings

def get_db_url():
    return f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.POSTGRES_DB}"

def get_active_cameras():
    """Возвращает список словарей {'id': 1, 'rtsp_url': '...'}"""
    engine = create_engine(get_db_url())
    cameras = []
    
    try:
        with engine.connect() as conn:
            # Выбираем только активные камеры
            result = conn.execute(text("SELECT id, rtsp_url FROM cameras WHERE is_active = true"))
            for row in result:
                cameras.append({"id": row[0], "rtsp_url": row[1]})
    except Exception as e:
        print(f"❌ Ошибка чтения БД: {e}")
    
    return cameras