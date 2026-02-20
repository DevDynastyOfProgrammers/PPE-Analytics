# # ingestor/debug_cv.py

# import cv2
# import os
# import sys

# file_path = "/app/debug_video.avi"

# print(f"--- DIAGNOSTIC START ---")
# print(f"Python: {sys.version}")
# print(f"OpenCV: {cv2.__version__}")

# if not os.path.exists(file_path):
#     print(f"❌ File not found: {file_path}")
#     exit(1)

# print(f"File exists. Size: {os.path.getsize(file_path)} bytes")

# # Пытаемся открыть
# cap = cv2.VideoCapture(file_path, cv2.CAP_FFMPEG)

# if not cap.isOpened():
#     print("❌ cap.isOpened() is False")
#     exit(1)

# print(f"✅ cap.isOpened() is True")
# print(f"Backend Name: {cap.getBackendName()}")
# print(f"Resolution: {cap.get(cv2.CAP_PROP_FRAME_WIDTH)}x{cap.get(cv2.CAP_PROP_FRAME_HEIGHT)}")

# # Пытаемся прочитать первый кадр
# print("Attempting to read frame 1...")
# ret, frame = cap.read()

# if ret:
#     print(f"✅ SUCCESS! Frame read. Shape: {frame.shape}")
# else:
#     print(f"❌ FAILURE! Frame read returned False.")
#     # Пытаемся получить код ошибки (работает в новых версиях)
#     try:
#         print(f"CV2 Error info: {cv2.compat.getTickCount()}") 
#     except:
#         pass

# cap.release()
# print("--- DIAGNOSTIC END ---")