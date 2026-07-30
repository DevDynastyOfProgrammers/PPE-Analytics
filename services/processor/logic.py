from collections import deque

from shapely.geometry import Point, Polygon


HISTORY_SECONDS = 3.0
MIN_TRACK_DURATION_SECONDS = 1.0
PPE_SCORE_THRESHOLD = 0.5
ALERT_DEBOUNCE_SECONDS = 10.0


class ViolationManager:
    """Накапливает историю PPE-статусов треков и подавляет дублирующие алерты."""

    def __init__(self):
        self.history = {}
        self.active_violations = {}

    def update_person(self, track_id, has_helmet, has_vest, current_time):
        """Обновляет историю трека и возвращает тип подтверждённого нарушения.

        Нарушение формируется, если после минимальной длительности трекинга
        средний PPE-score за скользящее окно ниже порога. Повторные алерты
        для того же трека подавляются в течение debounce-интервала.

        Args:
            track_id: Идентификатор трека человека.
            has_helmet: Обнаружена ли каска в текущем кадре.
            has_vest: Обнаружен ли жилет в текущем кадре.
            current_time: Время обработки кадра в секундах.

        Returns:
            Строку с типом нарушения или None, если алерт не требуется.
        """
        if track_id not in self.history:
            self.history[track_id] = deque()

        score = 0.0
        if has_helmet:
            score += 0.5
        if has_vest:
            score += 0.5

        track_history = self.history[track_id]
        track_history.append((current_time, score, has_helmet, has_vest))

        while (
            track_history
            and current_time - track_history[0][0] > HISTORY_SECONDS
        ):
            track_history.popleft()

        track_duration = current_time - track_history[0][0]
        if track_duration < MIN_TRACK_DURATION_SECONDS:
            return None

        average_score = sum(item[1] for item in track_history) / len(track_history)
        if average_score >= PPE_SCORE_THRESHOLD:
            self.active_violations.pop(track_id, None)
            return None

        total_frames = len(track_history)
        no_helmet_count = sum(1 for item in track_history if not item[2])
        no_vest_count = sum(1 for item in track_history if not item[3])

        violation_parts = []
        if no_helmet_count / total_frames > PPE_SCORE_THRESHOLD:
            violation_parts.append("no_helmet")
        if no_vest_count / total_frames > PPE_SCORE_THRESHOLD:
            violation_parts.append("no_vest")

        last_alert_time = self.active_violations.get(track_id)
        if (
            last_alert_time is not None
            and current_time - last_alert_time < ALERT_DEBOUNCE_SECONDS
        ):
            return None

        self.active_violations[track_id] = current_time
        return "+".join(violation_parts) if violation_parts else "no_ppe"


class GeometryChecker:
    """Проверяет попадание опорной точки человека в заданные зоны."""

    def check_zones(self, person_box, zones):
        """Возвращает первую зону, содержащую нижнюю центральную точку bbox.

        Нижняя центральная точка bounding box используется как приближённая
        позиция ног человека. Такой выбор снижает ложные попадания в зону,
        когда в неё пересекается только верхняя часть bounding box.

        Args:
            person_box: Координаты человека в формате [x1, y1, x2, y2].
            zones: Список API-представлений зон с polygon_coordinates.

        Returns:
            Кортеж (in_zone, zone_name, zone_id). Если точка не входит ни в
            одну корректную зону, возвращается (False, None, None).
        """
        x1, _, x2, y2 = person_box
        feet_point = Point((x1 + x2) / 2, y2)

        for zone in zones:
            coordinates = zone.get("polygon_coordinates")
            if not coordinates or len(coordinates) < 3:
                continue

            try:
                polygon = Polygon(coordinates)
            except (TypeError, ValueError):
                continue

            if polygon.contains(feet_point):
                return True, zone.get("name", "Zone"), zone.get("id")

        return False, None, None