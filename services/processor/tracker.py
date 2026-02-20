# processor/tracker.py

import numpy as np

class SimpleTracker:
    def __init__(self, max_lost=5, iou_threshold=0.3):
        self.next_id = 0
        self.tracks = {} # {track_id: {'bbox': [x1,y1,x2,y2], 'lost': 0}}
        self.max_lost = max_lost
        self.iou_threshold = iou_threshold

    def update(self, detections):
        """
        detections: список bbox'ов [[x1, y1, x2, y2], ...]
        Возвращает: список объектов с id [[x1, y1, x2, y2, track_id], ...]
        """
        if len(detections) == 0:
            for tid in list(self.tracks.keys()):
                self.tracks[tid]['lost'] += 1
                if self.tracks[tid]['lost'] > self.max_lost:
                    del self.tracks[tid]
            return []

        # 1. Вычисляем IOU между старыми треками и новыми детекциями
        matches = []
        unmatched_dets = list(range(len(detections)))
        
        track_ids = list(self.tracks.keys())
        
        if len(track_ids) > 0:
            iou_matrix = np.zeros((len(track_ids), len(detections)))
            for i, tid in enumerate(track_ids):
                for j, det in enumerate(detections):
                    iou_matrix[i, j] = self._iou(self.tracks[tid]['bbox'], det)

            # Жадное сопоставление
            if iou_matrix.size > 0:
                while True:
                    if iou_matrix.max() < self.iou_threshold:
                        break
                    i, j = np.unravel_index(iou_matrix.argmax(), iou_matrix.shape)
                    tid = track_ids[i]
                    matches.append((tid, detections[j]))
                    
                    # Удаляем из рассмотрения
                    iou_matrix[i, :] = -1
                    iou_matrix[:, j] = -1
                    if j in unmatched_dets:
                        unmatched_dets.remove(j)

        # 2. Обновляем совпавшие треки
        res = []
        for tid, bbox in matches:
            self.tracks[tid]['bbox'] = bbox
            self.tracks[tid]['lost'] = 0
            res.append(bbox + [tid])

        # 3. Создаем новые треки для несопоставленных детекций
        for idx in unmatched_dets:
            new_id = self.next_id
            self.next_id += 1
            self.tracks[new_id] = {'bbox': detections[idx], 'lost': 0}
            res.append(detections[idx] + [new_id])

        # 4. Удаляем потерянные треки
        for tid in list(self.tracks.keys()):
            if tid not in [m[0] for m in matches] and tid not in [r[-1] for r in res if r[-1] >= self.next_id - len(unmatched_dets)]:
                self.tracks[tid]['lost'] += 1
                if self.tracks[tid]['lost'] > self.max_lost:
                    del self.tracks[tid]

        return res

    def _iou(self, boxA, boxB):
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])
        interArea = max(0, xB - xA) * max(0, yB - yA)
        boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
        return interArea / float(boxAArea + boxBArea - interArea + 1e-6)