# processor/inference/detector.py

import numpy as np
import os
from ultralytics import YOLO

class HybridDetector:
    def __init__(self):
        print("🚀 Loading Models...")

        # 1. ЛЮДИ (Стандартная YOLOv8)
        person_model_path = "/app/models/yolov8n.pt"
        
        if os.path.exists(person_model_path):
            print(f"✅ Loading Person Model from local: {person_model_path}")
            self.person_model = YOLO(person_model_path) 
        else:
            print("⚠️ Local yolov8n.pt not found! Trying to download (will fail offline)...")
            self.person_model = YOLO("yolov8n.pt") 
        
        # 2. КАСКИ (ONNX)
        helmet_path = "/app/models/helmet_detector/1/model.onnx"
        if os.path.exists(helmet_path):
            print(f"✅ Loading Helmet Model: {helmet_path}")
            self.helmet_model = YOLO(helmet_path, task="detect")
        else:
            print(f"⚠️ Helmet model not found at {helmet_path}. Using fallback YOLOv8n.")
            self.helmet_model = None

        # 3. ЖИЛЕТЫ (ONNX)
        vest_path = "/app/models/vest_detector/1/model.onnx"
        if os.path.exists(vest_path):
            print(f"✅ Loading Vest Model: {vest_path}")
            self.vest_model = YOLO(vest_path, task="detect")
        else:
            print(f"⚠️ Vest model not found at {vest_path}. Using fallback YOLOv8n.")
            self.vest_model = None

        # Класс человека в COCO = 0
        self.person_class_id = 0 

    def detect_and_track(self, frame):
        """
        Возвращает:
        - tracked_persons: [[x1, y1, x2, y2, track_id], ...]
        - ppe_detections: {'helmets': [[x1,y1,x2,y2], ...], 'vests': [...]}
        """
        
        # --- 1. ЛЮДИ + ТРЕКИНГ ---
        person_results = self.person_model.track(
            frame, 
            persist=True, 
            classes=[self.person_class_id], 
            verbose=False,
            tracker="bytetrack.yaml"
        )
        
        tracked_persons = []
        if person_results and person_results[0].boxes and person_results[0].boxes.id is not None:
            boxes = person_results[0].boxes.xyxy.cpu().numpy()
            track_ids = person_results[0].boxes.id.int().cpu().numpy()
            
            for box, track_id in zip(boxes, track_ids):
                tracked_persons.append(box.tolist() + [int(track_id)])

        # --- 2. ДЕТЕКЦИЯ КАСОК ---
        helmets = []
        if self.helmet_model:
            # Запускаем инференс ONNX модели
            # conf=0.4 - порог уверенности
            h_results = self.helmet_model.predict(frame, verbose=False, conf=0.4)
            if h_results and h_results[0].boxes:
                helmets = h_results[0].boxes.xyxy.cpu().numpy().tolist()
        else:
            fallback_res = self.person_model.predict(frame, classes=[32], verbose=False, conf=0.2)
            if fallback_res and fallback_res[0].boxes:
                helmets = fallback_res[0].boxes.xyxy.cpu().numpy().tolist()

        # --- 3. ДЕТЕКЦИЯ ЖИЛЕТОВ ---
        vests = []
        if self.vest_model:
            v_results = self.vest_model.predict(frame, verbose=False, conf=0.4)
            if v_results and v_results[0].boxes:
                vests = v_results[0].boxes.xyxy.cpu().numpy().tolist()
        else:
            fallback_res = self.person_model.predict(frame, classes=[24], verbose=False, conf=0.2)
            if fallback_res and fallback_res[0].boxes:
                vests = fallback_res[0].boxes.xyxy.cpu().numpy().tolist()

        return tracked_persons, {'helmets': helmets, 'vests': vests}

# Фабрика
def get_detector():
    return HybridDetector()