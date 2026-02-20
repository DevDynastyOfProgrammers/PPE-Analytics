# ingestor/main.py

import time
import pika
from config import settings
from db_client import get_active_cameras
from video_stream import CameraStream

def main():
    print("--- Ingestor Service Started ---")
    
    # Параметры подключения к RabbitMQ для потоков
    rabbit_credentials = pika.PlainCredentials(settings.RABBITMQ_USER, settings.RABBITMQ_PASS)
    rabbit_params = pika.ConnectionParameters(
        host=settings.RABBITMQ_HOST, 
        port=settings.RABBITMQ_PORT, 
        credentials=rabbit_credentials
    )

    # Хранилище запущенных потоков: {camera_id: CameraStream}
    active_streams = {}

    while True:
        try:
            # 1. Получаем актуальный список камер из БД
            db_cameras = get_active_cameras()
            db_camera_ids = {cam['id'] for cam in db_cameras}
            
            # 2. Запускаем новые камеры
            for cam in db_cameras:
                cam_id = cam['id']
                if cam_id not in active_streams:
                    print(f"🚀 Starting stream for Camera {cam_id} ({cam['rtsp_url']})")
                    stream = CameraStream(cam_id, cam['rtsp_url'], rabbit_params)
                    stream.start()
                    active_streams[cam_id] = stream
            
            # 3. Останавливаем удаленные камеры (если их убрали из БД)
            active_ids = list(active_streams.keys())
            for cam_id in active_ids:
                if cam_id not in db_camera_ids:
                    print(f"💀 Stopping stream for Camera {cam_id} (removed from DB)")
                    active_streams[cam_id].stop()
                    active_streams[cam_id].join() # Ждем завершения
                    del active_streams[cam_id]
            
            # Пауза перед следующей проверкой базы данных (например, раз в 10 секунд)
            time.sleep(10)

        except Exception as e:
            print(f"Global Ingestor Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()