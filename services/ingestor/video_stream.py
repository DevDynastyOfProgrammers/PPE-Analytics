import cv2
import time
import threading
import json
import base64
import pika
import os
from config import settings

class CameraStream(threading.Thread):
    def __init__(self, camera_id, rtsp_url, rabbit_params):
        super().__init__()
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.rabbit_params = rabbit_params
        self.running = True
        # Поддержка числа как ID камеры (0 для вебки)
        self.video_source = int(self.rtsp_url) if str(self.rtsp_url).isdigit() else self.rtsp_url
        self.preview_saved = False 

    def connect_to_rabbitmq(self):
        while self.running:
            try:
                connection = pika.BlockingConnection(self.rabbit_params)
                channel = connection.channel()
                channel.queue_declare(queue=settings.QUEUE_NAME_FRAMES, durable=True)
                print(f"✅ [Cam {self.camera_id}] Connected to RabbitMQ")
                return connection, channel
            except pika.exceptions.AMQPConnectionError:
                print(f"⏳ [Cam {self.camera_id}] Waiting for RabbitMQ...")
                time.sleep(5)
        return None, None

    def save_preview(self, frame):
        """Сохраняет превью для UI. ВАЖНО: Размер должен совпадать с логикой процессора."""
        try:
            preview_dir = "/app/event_data/previews"
            os.makedirs(preview_dir, exist_ok=True)
            save_path = os.path.join(preview_dir, f"cam_{self.camera_id}.jpg")
            
            # Сохраняем как есть (уже отресайзено в цикле run), чтобы координаты совпадали
            cv2.imwrite(save_path, frame)
            # print(f"📸 [Cam {self.camera_id}] Preview saved: {save_path}")
            self.preview_saved = True
        except Exception as e:
            print(f"❌ [Cam {self.camera_id}] Failed to save preview: {e}")

    def run(self):
        print(f"📷 [Cam {self.camera_id}] STARTED. Source: {self.video_source}")
        
        connection, channel = self.connect_to_rabbitmq()
        if not connection: return 

        cap = cv2.VideoCapture(self.video_source, cv2.CAP_FFMPEG)
        
        # Ограничитель FPS
        prev_time = 0
        fps_delay = 1.0 / settings.FPS_LIMIT

        while self.running:
            time_elapsed = time.time() - prev_time
            if time_elapsed < fps_delay:
                time.sleep(0.01)
                continue
            prev_time = time.time()

            ret, frame = cap.read()
            if not ret:
                print(f"🔄 [Cam {self.camera_id}] Restarting video...")
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            # 1. Ресайз ДО всей логики (единый стандарт размера 640px по ширине)
            height, width = frame.shape[:2]
            if width != settings.FRAME_WIDTH:
                scale = settings.FRAME_WIDTH / width
                new_height = int(height * scale)
                frame = cv2.resize(frame, (settings.FRAME_WIDTH, new_height))

            # 2. Сохранение превью (один раз)
            if not self.preview_saved:
                self.save_preview(frame)

            # 3. Отправка в RabbitMQ
            try:
                _, buffer = cv2.imencode('.jpg', frame)
                img_str = base64.b64encode(buffer).decode('utf-8')

                msg = {
                    "camera_id": self.camera_id,
                    "timestamp": time.time(),
                    "frame_data": img_str
                }
                
                channel.basic_publish(
                    exchange='',
                    routing_key=settings.QUEUE_NAME_FRAMES,
                    body=json.dumps(msg)
                )
            except Exception as e:
                print(f"🔥 [Cam {self.camera_id}] Error sending frame: {e}")
                connection, channel = self.connect_to_rabbitmq()
                if not connection: break

        cap.release()
        if connection: connection.close()