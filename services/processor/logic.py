# processor/logic.py

from shapely.geometry import Point, Polygon
from collections import deque

class ViolationManager:
    def __init__(self):
        # Настройки
        self.HISTORY_SECONDS = 3.0   # Сколько секунд анализируем
        self.MIN_DURATION = 1.0      # Минимальное время трекинга перед решением
        self.PPE_THRESHOLD = 0.5     # Если СИЗ есть менее чем в 50% кадров -> Нарушение
        
        # Хранилище: {track_id: deque([(timestamp, has_ppe_score), ...])}
        # has_ppe_score: 1.0 (есть все), 0.5 (нет чего-то одного), 0.0 (нет ничего)
        self.history = {}
        self.active_violations = {} # {track_id: last_alert_time}

    def update_person(self, track_id, has_helmet, has_vest, current_time):
        """
        Возвращает строку нарушения или None.
        """
        if track_id not in self.history:
            self.history[track_id] = deque()

        # Вычисляем очки СИЗ для текущего кадра (0, 0.5 или 1)
        score = 0
        if has_helmet: score += 0.5
        if has_vest: score += 0.5
        
        # Добавляем в историю
        self.history[track_id].append((current_time, score, has_helmet, has_vest))

        # Удаляем старые записи (скользящее окно)
        while self.history[track_id] and (current_time - self.history[track_id][0][0] > self.HISTORY_SECONDS):
            self.history[track_id].popleft()

        # Если данных мало, выходим
        track_duration = current_time - self.history[track_id][0][0]
        if track_duration < self.MIN_DURATION:
            return None

        # АНАЛИЗ: Считаем средний скор за окно времени
        avg_score = sum(x[1] for x in self.history[track_id]) / len(self.history[track_id])

        # Если средний показатель СИЗ ниже порога (например, < 0.5, то есть меньше 50%)
        if avg_score < self.PPE_THRESHOLD:
            # Определяем, чего именно не хватает чаще всего
            no_helmet_cnt = sum(1 for x in self.history[track_id] if not x[2])
            no_vest_cnt = sum(1 for x in self.history[track_id] if not x[3])
            total = len(self.history[track_id])

            viol_parts = []
            if (no_helmet_cnt / total) > 0.5: viol_parts.append("no_helmet")
            if (no_vest_cnt / total) > 0.5: viol_parts.append("no_vest")
            
            violation_type = "+".join(viol_parts) if viol_parts else "no_ppe"

            # Debounce: не спамим, если уже отправляли алерт по этому треку недавно (10 сек)
            if track_id in self.active_violations:
                if current_time - self.active_violations[track_id] < 10.0:
                    return None
            
            self.active_violations[track_id] = current_time
            return violation_type

        # Если человек исправился (надел СИЗ), сбрасываем активное нарушение
        if avg_score >= self.PPE_THRESHOLD and track_id in self.active_violations:
            del self.active_violations[track_id]

        return None

class GeometryChecker:
    def check_zones(self, person_box, zones):
        x1, y1, x2, y2 = person_box
        # Точка проверки: середина нижнего края (ноги)
        feet_point = Point((x1 + x2) / 2, y2)
        
        for zone in zones:
            coords = zone.get('polygon_coordinates')
            if not coords or len(coords) < 3: continue
            
            try:
                poly = Polygon(coords)
                if poly.contains(feet_point):
                    return True, zone.get('name', 'Zone'), zone.get('id')
            except:
                pass
                
        return False, None, None