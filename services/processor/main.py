import pika
import json
import numpy as np
import cv2
import base64
import time
import os
import uuid
import requests
from datetime import datetime, timezone
from config import settings
from inference.detector import get_detector
from logic import ViolationManager, GeometryChecker

EVENT_DATA_DIR = "/app/event_data"
os.makedirs(EVENT_DATA_DIR, exist_ok=True)

detector = get_detector()
violation_manager = ViolationManager()
geo_checker = GeometryChecker()

ZONES_CACHE = {} 
LAST_ZONES_UPDATE = 0

STREAM_QUEUE_NAME = "processed_stream_queue"

def update_zones_cache(camera_id):
    """Запрашиваем зоны для конкретной камеры из API"""
    global LAST_ZONES_UPDATE, ZONES_CACHE
    
    # Не обращаемся к API чаще раза в 5 секунд для одной камеры
    if time.time() - LAST_ZONES_UPDATE < 5:
        return ZONES_CACHE.get(camera_id, [])

    try:
        url = f"{settings.API_SERVER_URL}/cameras/{camera_id}/zones"
        resp = requests.get(url, timeout=2)
        if resp.status_code == 200:
            zones = resp.json()
            ZONES_CACHE[camera_id] = zones
            LAST_ZONES_UPDATE = time.time()
    except Exception as e:
        print(f"⚠️ Failed to update zones: {e}")
    
    return ZONES_CACHE.get(camera_id, [])

def save_evidence(frame, violation_type, track_id, bbox):
    """Сохраняет кадр с отрисовкой"""
    now_utc = datetime.now(timezone.utc)
    date_str = now_utc.strftime("%Y-%m-%d")
    folder = os.path.join(EVENT_DATA_DIR, date_str)
    os.makedirs(folder, exist_ok=True)
    
    filename = f"{date_str}_{track_id}_{uuid.uuid4().hex[:6]}.jpg"
    path = os.path.join(folder, filename)
    
    # Рисуем
    img = frame.copy()
    x1, y1, x2, y2 = map(int, bbox)
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
    cv2.putText(img, f"VIOLATION: {violation_type}", (x1, y1-10), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)
    
    cv2.imwrite(path, img)
    return f"/static/{date_str}/{filename}" # URL для API

def send_processed_frame(channel, camera_id, frame, detections, zones):
    """
    1. Рисует зоны и боксы на кадре.
    2. Отправляет кадр в RabbitMQ для просмотра в реальном времени.
    """
    # --- 1. РИСУЕМ ЗОНЫ (Зеленые линии) ---
    for zone in zones:
        coords = zone.get('polygon_coordinates')
        if coords and len(coords) > 2:
            pts = np.array(coords, np.int32)
            pts = pts.reshape((-1, 1, 2))
            # Рисуем полигон (True = замкнутый), Цвет (0, 255, 0) - Зеленый, Толщина 2
            cv2.polylines(frame, [pts], True, (0, 255, 0), 2)
            
            # Подписываем зону (берем первую точку)
            txt_pos = (pts[0][0][0], pts[0][0][1] - 10)
            cv2.putText(frame, zone.get('name', 'Zone'), txt_pos, 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    # --- 2. РИСУЕМ ЛЮДЕЙ И СТАТУСЫ ---
    for det in detections:
        x1, y1, x2, y2, track_id, has_helmet, has_vest = det
        
        # Логика цвета: Зеленый (все ок), Желтый (нет чего-то одного), Красный (нет ничего)
        if has_helmet and has_vest:
            color = (0, 255, 0) # Green
        elif not has_helmet and not has_vest:
            color = (0, 0, 255) # Red
        else:
            color = (0, 255, 255) # Yellow/Cyan (в BGR это желтый или голубой, тут желтый)

        # Рисуем бокс
        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
        
        # Текст над головой
        label = f"ID:{track_id}"
        if not has_helmet: label += " NoH" # Нет каски
        if not has_vest: label += " NoV"   # Нет жилета
        
        cv2.putText(frame, label, (int(x1), int(y1)-10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    # --- 3. ОТПРАВЛЯЕМ В RABBITMQ ---
    try:
        # Ресайзим для ускорения передачи (если кадр огромный), но у нас уже 640px, так что ок.
        # Сжимаем в JPEG с качеством 60% (баланс скорости и качества)
        _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
        img_str = base64.b64encode(buffer).decode('utf-8')
        
        msg = {
            "camera_id": camera_id,
            "frame_data": img_str
        }
        
        # Отправляем
        channel.basic_publish(
            exchange='',
            routing_key=settings.QUEUE_NAME_STREAM, 
            body=json.dumps(msg)
        )
    except Exception as e:
        print(f"Stream send error: {e}")

def callback(ch, method, properties, body):
    try:
        # 1. Декодируем сообщение
        msg = json.loads(body)
        camera_id = msg['camera_id']
        img_bytes = base64.b64decode(msg['frame_data'])
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        current_time = time.time()

        # 2. Получаем зоны (кэшированные или запрос к API)
        zones = update_zones_cache(camera_id)
        
        # Список для сбора данных об объектах (чтобы потом нарисовать)
        # Формат: (x1, y1, x2, y2, track_id, has_helmet, has_vest)
        visual_detections = []

        if zones: # Обрабатываем, только если есть зоны (или убери if, если хочешь детектить всегда)
            
            # 3. Детекция + Трекинг
            tracked_persons, ppe_data = detector.detect_and_track(frame)
            
            helmets = ppe_data['helmets']
            vests = ppe_data['vests']

            for p in tracked_persons:
                px1, py1, px2, py2, track_id = p
                p_box = [px1, py1, px2, py2]
                
                # --- Проверка СИЗ (Пересечение боксов) ---
                has_helmet = False
                for h in helmets:
                    hx, hy = (h[0]+h[2])/2, (h[1]+h[3])/2 # Центр каски
                    if px1 < hx < px2 and py1 < hy < py2: # Центр каски внутри бокса человека
                        has_helmet = True
                        break
                
                has_vest = False
                for v in vests:
                    vx, vy = (v[0]+v[2])/2, (v[1]+v[3])/2 # Центр жилета
                    if px1 < vx < px2 and py1 < vy < py2:
                        has_vest = True
                        break
                
                # Сохраняем инфу для отрисовки (даже если не в зоне)
                visual_detections.append((px1, py1, px2, py2, track_id, has_helmet, has_vest))

                # --- Проверка Гео-зон ---
                in_zone, zone_name, zone_id = geo_checker.check_zones(p_box, zones)
                
                if in_zone:
                    # 4. Бизнес-логика нарушений (Timer / Threshold)
                    violation = violation_manager.update_person(
                        track_id, has_helmet, has_vest, current_time
                    )

                    if violation:
                        print(f"🚨 ALERT: {violation} | Cam {camera_id} | Zone {zone_name}")
                        
                        # Сохраняем фото нарушения (Evidence)
                        url = save_evidence(frame, violation, track_id, p_box)
                        
                        # Отправляем алерт
                        alert = {
                            "camera_id": camera_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "violation_type": violation,
                            "track_id": track_id,
                            "snapshot_url": url,
                            "zone_id": zone_id
                        }
                        
                        ch.basic_publish(
                            exchange='',
                            routing_key=settings.QUEUE_NAME_ALERTS,
                            body=json.dumps(alert),
                            properties=pika.BasicProperties(delivery_mode=2)
                        )

        # --- 5. ОТПРАВКА КАДРА В LIVE VIEW ---
        # Отправляем всегда, даже если зон нет (чтобы видеть чистый поток)
        send_processed_frame(ch, camera_id, frame, visual_detections, zones)

    except Exception as e:
        print(f"Error processing frame: {e}")

    # Подтверждаем обработку сообщения
    ch.basic_ack(delivery_tag=method.delivery_tag)

def main():
    print(f"Processor Starting... Mode: Hybrid")
    credentials = pika.PlainCredentials(settings.RABBITMQ_USER, settings.RABBITMQ_PASS)
    params = pika.ConnectionParameters(host=settings.RABBITMQ_HOST, port=settings.RABBITMQ_PORT, credentials=credentials)
    
    while True:
        try:
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.queue_declare(queue=settings.QUEUE_NAME_FRAMES, durable=True)
            channel.queue_declare(queue=settings.QUEUE_NAME_ALERTS, durable=True)

            # --- Очередь для стрима ---
            # durable=False, так как это поток, старые кадры нам не нужны после перезагрузки
            channel.queue_declare(
                queue=settings.QUEUE_NAME_STREAM,
                durable=False,
                arguments={
                    "x-max-length": 2,
                    "x-overflow": "drop-head",
                },
            )

            channel.basic_qos(prefetch_count=1)
            
            print(" [*] Waiting for frames...")
            channel.basic_consume(queue=settings.QUEUE_NAME_FRAMES, on_message_callback=callback)
            channel.start_consuming()
        except Exception as e:
            print(f"Connection failed: {e}. Retrying...")
            time.sleep(5)

if __name__ == "__main__":
    main()