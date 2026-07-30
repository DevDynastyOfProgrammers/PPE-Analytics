import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk, ImageOps
import os
import platform
import subprocess
import shutil 
import base64
from ultralytics.utils import LOGGER
LOGGER.setLevel("ERROR")
from ttkbootstrap import Style
import requests
import pika
import json
import io
from threading import Thread

SERVER_IP = "localhost"
API_PORT = "8888"  
RABBIT_PORT = 5672
RABBIT_USER = "guest"
RABBIT_PASS = "guest"


class ServerClient:
    """Класс для общения с Бэкендом"""

    def __init__(self, on_alert_callback):
        self.api_url = f"http://{SERVER_IP}:{API_PORT}"
        self.on_alert_callback = on_alert_callback
        self.is_connected = False
        self.rabbit_thread = None

    def get_cameras(self):
        """Получает список активных камер с сервера"""
        if not self.is_connected:
            return []
        try:
            resp = requests.get(f"{self.api_url}/cameras/", timeout=5)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            print(f"Ошибка получения списка камер: {e}")
        return []

    def get_preview(self, camera_id):
        """Скачивает превью для конкретной камеры"""
        url = f"/static/previews/cam_{camera_id}.jpg"
        return self.get_image_from_url(url)

    def get_image_from_url(self, relative_url):
        """Скачивает картинку по URL и возвращает объект PIL Image"""
        try:
            full_url = f"{self.api_url}{relative_url}"
            resp = requests.get(full_url, timeout=2)
            if resp.status_code == 200:
                return Image.open(io.BytesIO(resp.content))
        except Exception as e:
            print(f"Ошибка загрузки фото ({relative_url}): {e}")
        return None

    def check_connection(self):
        """Проверка доступности API"""
        try:
            resp = requests.get(f"{self.api_url}/cameras/", timeout=3)
            return resp.status_code == 200
        except Exception as e:
            print(f"Ошибка подключения к API: {e}")
            return False
    
    # 🟡 ИЗМЕНЕНО: Метод для отправки зоны
    def send_zone(self, camera_id, points, name="Zone"):
        """Отправляет зону на сервер"""
        try:
            payload = {
                "name": name,
                "camera_id": camera_id,
                "polygon_coordinates": points # [[x,y], [x,y]]
            }
            resp = requests.post(f"{self.api_url}/zones/", json=payload, timeout=2)
            if resp.status_code == 200:
                print("✅ Зона успешно отправлена на сервер")
                return True
            else:
                print(f"❌ Ошибка сервера при сохранении зоны: {resp.text}")
        except Exception as e:
            print(f"❌ Ошибка отправки зоны: {e}")
        return False

    def start_listening(self):
        """Запуск прослушки RabbitMQ в отдельном потоке"""
        self.is_connected = True
        self.rabbit_thread = Thread(target=self._rabbit_worker, daemon=True)
        self.rabbit_thread.start()

    def stop_listening(self):
        self.is_connected = False

    def _rabbit_worker(self):
        """Внутренняя логика работы с RabbitMQ"""
        try:
            credentials = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)
            parameters = pika.ConnectionParameters(SERVER_IP, RABBIT_PORT, '/', credentials)
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()

            # 🟡 ИЗМЕНЕНО: Очередь должна совпадать с той, куда пишет processor
            queue_name = 'violation_alerts_queue'
            channel.queue_declare(queue=queue_name, passive=True)

            print("✅ Подключено к RabbitMQ. Жду алерты...")

            def callback(ch, method, properties, body):
                if not self.is_connected:
                    ch.stop_consuming()
                    connection.close()
                    return

                alert_data = json.loads(body)
                # Вызываем callback в GUI
                self.on_alert_callback(alert_data)

            channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)
            channel.start_consuming()

        except Exception as e:
            print(f"Ошибка RabbitMQ: {e}")
            self.is_connected = False

    # 🟡 ИЗМЕНЕНО: Методы для стриминга видеопотока
    # Внутри ServerClient

    def start_stream_listening(self, callback):
        """Запускает поток. callback(cam_id, image) будет вызываться для каждого кадра"""
        if self.rabbit_thread and self.rabbit_thread.is_alive():
            return # Уже запущено
            
        self.rabbit_thread = Thread(target=self._stream_worker, args=(callback,), daemon=True)
        self.rabbit_thread.start()

    def _stream_worker(self, callback):
        try:
            credentials = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)
            parameters = pika.ConnectionParameters(SERVER_IP, RABBIT_PORT, '/', credentials)
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            
            queue_name = 'processed_stream_queue'
            channel.queue_declare(queue=queue_name, passive=True)

            def on_frame(ch, method, props, body):
                try:
                    data = json.loads(body)
                    cam_id = data.get('camera_id')
                    b64_data = data.get('frame_data')
                    
                    if b64_data and cam_id is not None:
                        img_bytes = base64.b64decode(b64_data)
                        image = Image.open(io.BytesIO(img_bytes))
                        callback(cam_id, image)
                except Exception as e:
                    pass # Игнорируем битые кадры

            channel.basic_consume(queue=queue_name, on_message_callback=on_frame, auto_ack=True)
            channel.start_consuming()
        except Exception as e:
            print(f"Stream Connection Error: {e}")
            self.is_connected = False


class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event=None):
        if self.tooltip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 10

        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True) 
        tw.wm_geometry(f"+{x}+{y}")

        label = tk.Label(tw, text=self.text, justify='left',
                         background="#FFFFE0", relief='solid', borderwidth=1,
                         font=("Arial", 10))
        label.pack(ipadx=5, ipady=3)

    def hide_tooltip(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None


class VideoProcessorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Система Жилетка")
        self.root.geometry("600x500")
        
        self.server = ServerClient(on_alert_callback=self.handle_new_alert)
        self.violation = 0
        self.active_violations = [] # Список путей к локальным файлам
        self.violation_img = ["Нарушение зафиксировано\n"]
        self.drawing_enabled = False
        self.points = []
        self.temp_lines = []
        self.mask_polygon = None
        self.masks = []
        self.camera_error = 0
        self.camera_error_id = []
        # 🟡 ИЗМЕНЕНО: переменные для отображения камер
        self.live_widgets = {}     # {cam_id: label_in_grid}
        self.detail_window = None  # Окно детального просмотра
        self.detail_label = None   # Лейбл в детальном окне
        self.detail_cam_id = None  # ID камеры в детальном окне

        # Сразу запускаем слушателя стрима
        # Он будет работать в фоне и обновлять интерфейс, когда открыты окна
        self.server.start_stream_listening(self.dispatch_frame)

        # 🟡 ИЗМЕНЕНО: Создаем папку для сохранения скачанных фото нарушений, если нет
        self.local_viol_dir = "viol_detect"
        os.makedirs(self.local_viol_dir, exist_ok=True)

        self.create_start_window()
        self.check_violations = []

    def create_start_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        start_frame = ttk.Frame(self.root, padding=40)
        start_frame.pack(expand=True)

        start_btn = ttk.Button(start_frame, text="Начать", command=self.connect_to_server, padding=(40, 20))
        start_btn.pack(pady=20)

        Tooltip(start_btn, "Подключиться к серверу")

    def connect_to_server(self):
        self.root.update() 

        if self.server.check_connection():
            self.server.start_listening()
            self.root.after(500, self.main_window)
        else:
            messagebox.showerror("Ошибка",
                                 f"Не удалось подключиться к серверу {SERVER_IP}.\nПроверьте сеть и запущен ли Backend.")

    def handle_new_alert(self, alert_data):
        """
        🟡 ИЗМЕНЕНО: Логика обработки алерта.
        Скачивает фото и обновляет интерфейс.
        """
        try:
            print(f"⚡ Получен алерт: {alert_data.get('violation_type')}")
            
            # 1. Получаем URL картинки
            snapshot_url = alert_data.get("snapshot_url")
            if snapshot_url:
                # 2. Скачиваем картинку
                img = self.server.get_image_from_url(snapshot_url)
                if img:
                    # 3. Сохраняем локально (т.к. текущий UI работает с файлами)
                    # Генерируем имя файла из времени или ID
                    filename = f"viol_{len(self.active_violations)}_{alert_data.get('camera_id')}.jpg"
                    local_path = os.path.join(self.local_viol_dir, filename)
                    img.save(local_path)
                    
                    # 4. Обновляем данные (в главном потоке Tkinter)
                    def update_ui():
                        self.active_violations.append(local_path)
                        self.violation += 1
                        self.update_violation_log()
                        # Можно добавить всплывающее уведомление или звук
                    
                    self.root.after(0, update_ui)
        except Exception as e:
            print(f"Ошибка обработки алерта: {e}")

    # 🟡 ИЗМЕНЕНО: отображение всех камер
    def open_live_view(self):
        """Открывает окно мониторинга со всеми камерами (СЕТКА)"""
        
        # Очищаем старый список виджетов перед открытием
        self.live_widgets = {}
        
        # Создаем окно
        monitor_window = tk.Toplevel(self.root)
        monitor_window.title("Мониторинг (Все камеры)")
        monitor_window.geometry("1000x700")
        
        # Загружаем список камер
        cameras = self.server.get_cameras()
        if not cameras:
            tk.Label(monitor_window, text="Нет активных камер").pack(pady=20)
            return

        # Настройка сетки (адаптивная)
        columns = 3 # Количество колонок
        
        # Растягиваем колонки
        for i in range(columns):
            monitor_window.columnconfigure(i, weight=1)
        
        # Создаем ячейки
        for i, cam in enumerate(cameras):
            cam_id = cam['id']
            cam_name = cam['name']
            
            row = i // columns
            col = i % columns
            monitor_window.rowconfigure(row, weight=1)
            
            # Фрейм для одной камеры
            cell_frame = ttk.Frame(monitor_window, borderwidth=2, relief="groove")
            cell_frame.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)
            cell_frame.columnconfigure(0, weight=1)
            cell_frame.rowconfigure(1, weight=1) # Картинка занимает место
            
            # Заголовок
            ttk.Label(cell_frame, text=f"{cam_name} (ID: {cam_id})", font=("Arial", 9, "bold")).grid(row=0, column=0, sticky="ew", padx=5)
            
            # Лейбл для видео (изначально черный квадрат)
            video_label = tk.Label(cell_frame, bg="black", cursor="hand2")
            video_label.grid(row=1, column=0, sticky="nsew")
            
            # При клике открываем детальный вид
            # Используем lambda с замыканием, чтобы запомнить cam_id
            video_label.bind("<Button-1>", lambda e, c_id=cam_id, c_name=cam_name: self.open_detail_view(c_id, c_name))
            
            # Регистрируем виджет, чтобы dispatch_frame знал, куда рисовать
            self.live_widgets[cam_id] = video_label

            # Загружаем статичное превью для начала (чтобы не было черного экрана до первого кадра)
            preview = self.server.get_preview(cam_id)
            if preview:
                # Предварительный ресайз для сетки
                preview = ImageOps.contain(preview, (300, 200))
                ph = ImageTk.PhotoImage(preview)
                video_label.configure(image=ph)
                video_label.image = ph

    # 🟡 ИЗМЕНЕНО: отображение выбранной камеры в новом окне
    def open_detail_view(self, cam_id, cam_name):
        """Открывает большое окно для одной камеры"""
        
        # Если уже открыто - закрываем старое (или выводим на передний план)
        if self.detail_window and self.detail_window.winfo_exists():
            self.detail_window.destroy()
            
        self.detail_cam_id = cam_id
        
        self.detail_window = tk.Toplevel(self.root)
        self.detail_window.title(f"Камера: {cam_name}")
        self.detail_window.geometry("800x600")
        
        # Лейбл на всё окно
        self.detail_label = tk.Label(self.detail_window, bg="black")
        self.detail_label.pack(expand=True, fill="both")
        
        # Сразу ставим превью, пока ждем стрим
        preview = self.server.get_preview(cam_id)
        if preview:
            preview = ImageOps.contain(preview, (800, 600))
            ph = ImageTk.PhotoImage(preview)
            self.detail_label.configure(image=ph)
            self.detail_label.image = ph

    def update_live_image(self, cam_id, image):
        """Этот метод вызывается из потока RabbitMQ, когда пришел новый кадр"""
        # Проверяем, живо ли окно. Если пользователь его закрыл - выходим.
        if not hasattr(self, 'live_window') or not self.live_window.winfo_exists():
            return
        
        try:
            # Получаем текущие размеры окна, чтобы растянуть картинку
            win_w = self.live_window.winfo_width()
            win_h = self.live_window.winfo_height()
            
            # Если окно только открылось, оно может выдавать размер 1x1, ставим дефолт
            if win_w < 100: win_w = 800
            if win_h < 100: win_h = 600

            # Ресайзим картинку под размер окна (красиво, сохраняя пропорции crop/fit)
            # Или просто resize, если хотим растянуть: image = image.resize((win_w, win_h))
            image = ImageOps.fit(image, (win_w, win_h), centering=(0.5, 0.5))
            
            photo = ImageTk.PhotoImage(image)
            
            # ВАЖНО: Обновление GUI должно быть в главном потоке
            def _update_ui():
                if not self.live_window.winfo_exists(): return
                self.live_label.config(image=photo)
                self.live_label.image = photo # Ссылка, чтобы сборщик мусора не удалил
            
            # self.root.after(0, func) ставит задачу в очередь главного потока
            self.root.after(0, _update_ui)
            
        except Exception as e:
            print(f"UI Update Error: {e}")

    def main_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        cameras_data = self.server.get_cameras()
        self.number_cameras = []
        self.camera_error = 0
        self.camera_error_id = []
        for i, cam_info in enumerate(cameras_data):
            cam_id = cam_info['id']
            img = self.server.get_preview(cam_id)
            if img is None:
                self.camera_error += 1
                self.camera_error_id.append(cam_id)
            else:
                self.number_cameras.append(cam_id)

        self.root.columnconfigure(0, weight=3)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=0)

        log_frame = ttk.Frame(self.root)
        log_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        log_frame.columnconfigure(0, weight=3)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            bg="#B0B0B0",
            fg="lime",
            insertbackground="white",
            state="disabled",
            font=("Consolas", 12)
        )
        self.log_text.configure(width=1, height=1)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.tag_config("INFO", foreground="black")
        self.log_text.tag_config("WARN", foreground="orange")
        self.log_text.tag_config("ERROR", foreground="red")

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        btn_frame = ttk.Frame(self.root)
        btn_frame.grid(row=0, column=1, sticky="n", padx=10, pady=10)
        btn_frame.columnconfigure(0, weight=1)

        stop_btn = ttk.Button(btn_frame, text="Стоп", command=self.create_start_window, padding=(30, 10))
        stop_btn.grid(row=0, column=0, pady=5, sticky="ew")
        Tooltip(stop_btn, "Остановить подключение к серверу")

        mask_btn = ttk.Button(btn_frame, text="Безопасная область", command=self.camera_window, padding=(30, 10))
        mask_btn.grid(row=1, column=0, pady=5, sticky="ew")
        Tooltip(mask_btn, "Создание области, в которой система работать не будет")

        viol_btn = ttk.Button(btn_frame, text="Нарушения", command=self.all_viol_window, padding=(30, 10))
        viol_btn.grid(row=2, column=0, pady=5, sticky="ew")
        Tooltip(viol_btn, "Обработка нарушений")

        viol_btn = ttk.Button(btn_frame, text="Настройки", command=self.create_input_window, padding=(30, 10))
        viol_btn.grid(row=3, column=0, pady=5, sticky="ew")
        
        # 🟡 ИЗМЕНЕНО: кнопка запуска LIVE просмотра
        live_btn = ttk.Button(btn_frame, text="🔴 LIVE Просмотр", command=self.open_live_view, padding=(30, 10))
        live_btn.grid(row=4, column=0, pady=5, sticky="ew") # row=4 (или следующий свободный)
        Tooltip(live_btn, "Смотреть, как нейросеть работает в реальном времени")

        def add_log(msg, level="INFO"):
            self.log_text.config(state="normal")
            self.log_text.insert("end", msg + "\n", level)
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        
        if self.violation > 0:
            add_log(f"Обнаружено нарушений - {self.violation}", "ERROR")
        else:
            add_log(f"Обнаружено нарушений - 0")
        if self.camera_error > 0:
            add_log(f"Проблем с камерами - {self.camera_error}", "WARN")
        else:
            add_log("Проблем с камерами нет")
        if self.camera_error > 0:
            for i in self.camera_error_id:
                add_log(f"Камера id_{i} не работает", "ERROR")
        for i in self.number_cameras:
            add_log(f"Камера id_{i} работает")
        self.add_log = add_log

    def update_violation_log(self):
        # 🟡 ИЗМЕНЕНО: защита от падения ПО
        if not hasattr(self, 'log_text'):
            return
        msg = f"Обнаружено нарушений - {self.violation}"
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "2.0")
        self.log_text.insert("1.0", msg + "\n", "ERROR")
        self.log_text.config(state="disabled")


    def camera_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        cameras_data = self.server.get_cameras()
        if not cameras_data:
            print("Внимание: Список камер пуст или нет связи.")

        columns = 4
        self.button_images = []
        self.orig_images = []

        button_size = 120
        padding = 5

        cameras_frame = tk.Frame(self.root)
        cameras_frame.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=85)
        self.root.rowconfigure(1, weight=15)
        self.root.columnconfigure(0, weight=1)

        error_img_path = "camera_previev/camera_error.jpg"
        if os.path.exists(error_img_path):
            default_img = Image.open(error_img_path)
        else:
            default_img = Image.new('RGB', (320, 240), color='black')

        for i, cam_info in enumerate(cameras_data):
            cam_id = cam_info['id']
            cam_name = cam_info['name']

            row = i // columns
            col = i % columns

            img = self.server.get_preview(cam_id)

            if img is None:
                img = default_img
                self.camera_error += 1

            self.orig_images.append(img)
            photo = ImageTk.PhotoImage(img.resize((button_size, button_size)))
            self.button_images.append(photo)

            btn = tk.Button(
                cameras_frame,
                text=f"{cam_name} (ID: {cam_id})",
                image=photo,
                compound="center",
                fg="white",
                font=("Arial", 10, "bold"),
                bd=0,
                highlightthickness=0,
                command=lambda c_id=cam_id: self.mask_window(c_id)
            )
            btn.grid(row=row, column=col, padx=padding, pady=padding, sticky="nsew")

            def resize_image(event, index=i, button=btn):
                new_width = event.width
                new_height = event.height
                if index < len(self.orig_images):
                    img_resized = ImageOps.fit(self.orig_images[index], (new_width, new_height), centering=(0.5, 0.5))
                    photo_new = ImageTk.PhotoImage(img_resized)
                    self.button_images[index] = photo_new
                    button.config(image=photo_new)

            btn.bind("<Configure>", resize_image)

        for col in range(columns):
            cameras_frame.columnconfigure(col, weight=1)
        if cameras_data:
            total_rows = (len(cameras_data) + columns - 1) // columns
            for row in range(total_rows):
                cameras_frame.rowconfigure(row, weight=1)

        bottom_frame = tk.Frame(self.root)
        bottom_frame.grid(row=1, column=0, sticky="nsew")
        bottom_frame.columnconfigure(0, weight=1)
        bottom_frame.rowconfigure(0, weight=1)

        back_btn = tk.Button(bottom_frame, text="Назад", width=20, command=self.main_window)
        back_btn.grid(row=0, column=0, pady=10)

    def on_canvas_click(self, event):
        if not self.drawing_enabled:
            return
        x, y = event.x, event.y
        self.points.append((x, y))

        r = 4
        self.canvas.create_oval(x - r, y - r, x + r, y + r, fill="green", outline="green")

        if len(self.points) > 1:
            x1, y1 = self.points[-2]
            line = self.canvas.create_line(x1, y1, x, y, fill="green", width=2)
            self.temp_lines.append(line)

    def save_mask_to_file(self, camera_index, points):
        folder = "masks"
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"camera_{camera_index}.txt") # 🟡 Fix: camera_index is ID now
        line = " ".join([f"{x},{y}" for x, y in points])
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def load_mask_from_file(self, camera_index):
        mask_path = f"masks/camera_{camera_index}.txt" # 🟡 Fix

        if not os.path.exists(mask_path):
            return None

        shapes = []
        with open(mask_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                shape = []
                for pair in line.split():
                    x_str, y_str = pair.split(",")
                    x, y = int(x_str), int(y_str)
                    shape.append((x, y))
                shapes.append(shape)
        return shapes

    def delete_mask_file(self, camera_index):
        mask_path = f"masks/camera_{camera_index}.txt" # 🟡 Fix
        if os.path.exists(mask_path):
            os.remove(mask_path)
            print(f"Файл {mask_path} удалён.")
        else:
            print(f"Файл {mask_path} не найден.")

    def mask_window(self, camera_index):
        for widget in self.root.winfo_children():
            widget.destroy()

        # img = self.server.get_preview(camera_index)

        # if img is None:
        #     error_img_path = "camera_previev/camera_error.jpg"
        #     if os.path.exists(error_img_path):
        #         img = Image.open(error_img_path)
        #     else:
        #         img = Image.new('RGB', (800, 600), color='gray')

        # win_width = self.root.winfo_width()
        # win_height = self.root.winfo_height()
        # if win_width == 1:
        #     win_width = 800
        #     win_height = 600

        # btn_area_height = int(win_height * 0.15)
        # bg_height = win_height - btn_area_height

        # Загружаем превью
        img = self.server.get_preview(camera_index)
        
        if img is None:    
            error_img_path = "camera_previev/camera_error.jpg"    
            if os.path.exists(error_img_path):        
                img = Image.open(error_img_path)    
            else:        
                img = Image.new('RGB', (640, 640), color='gray')  # fallback# 🟢 Всегда приводим картинку к размеру 640×640
        img = img.resize((640, 640), Image.LANCZOS)
        win_width = self.root.winfo_width()
        win_height = self.root.winfo_height()

        if win_width == 1:    
            win_width = 800    
            win_height = 600
        btn_area_height = int(win_height * 0.15)
        bg_height = win_height - btn_area_height
        # 🟡 ИЗМЕНЕНО: Важный момент масштабирования
        # Backend ожидает координаты для картинки 640x (как в ingestor).
        # Frontend растягивает картинку под окно. 
        # Чтобы зоны работали корректно, лучше всего рисовать их
        # когда размер окна близок к размеру видео. 
        # Или же нужно делать сложную математику масштабирования, 
        # которую сложно внедрить без переписывания класса.
        # Пока оставляем как есть, но помните об этом.
        
        img_bg = ImageOps.fit(img, (win_width, bg_height), centering=(0.5, 0.5))
        self.bg_photo = ImageTk.PhotoImage(img_bg)

        canvas = tk.Canvas(self.root, width=win_width, height=bg_height, highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        canvas.create_image(0, 0, anchor="nw", image=self.bg_photo)

        btn_frame = tk.Frame(self.root, height=btn_area_height)
        btn_frame.grid(row=1, column=0, sticky="ew", pady=5)

        self.root.rowconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=0)
        self.root.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.root, width=win_width, height=win_height)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_photo)

        loaded_points = self.load_mask_from_file(camera_index)
        self.masks = []

        if loaded_points:
            for shape in loaded_points:
                try:
                    flat = [coord for point in shape for coord in point]
                    polygon = self.canvas.create_polygon(
                        flat,
                        outline="green",
                        fill="green",
                        stipple="gray50",
                        width=2
                    )
                    self.masks.append(polygon)
                except Exception as e:
                    print("Ошибка при создании фигуры:", e)

        self.mask_points = []
        self.drawing = False

        def start_border_draw():
            self.drawing_enabled = True
            self.points.clear()

            if self.mask_polygon:
                self.canvas.delete(self.mask_polygon)
                self.mask_polygon = None

            for line in self.temp_lines:
                self.canvas.delete(line)
            self.temp_lines.clear()

        self.canvas.bind("<Button-1>", self.on_canvas_click)

        def save_mask():
            if len(self.points) < 3:
                return

            for line in self.temp_lines:
                self.canvas.delete(line)
            self.temp_lines.clear()

            flat_points = [coord for p in self.points for coord in p]

            polygon = self.canvas.create_polygon(
                flat_points,
                outline="green",
                fill="green",
                stipple="gray50",
                width=2
            )

            self.masks.append(polygon)
            self.drawing_enabled = False
            
            # 🟡 ИЗМЕНЕНО: Сохраняем в файл (старое) + Шлем на сервер (новое)
            self.save_mask_to_file(camera_index, self.points)
            self.server.send_zone(camera_index, self.points, name=f"UserZone_{len(self.masks)}")
            
            self.points.clear()

        def clear_mask():
            for item in self.canvas.find_all():
                self.canvas.delete(item)

            self.points.clear()
            self.temp_lines.clear()

            for poly in self.masks:
                self.canvas.delete(poly)
            self.masks.clear()

            self.drawing_enabled = False
            self.delete_mask_file(camera_index)
            
            # 🟡 TODO: Если нужно удалять зоны и с сервера, нужен endpoint DELETE
            # Пока просто чистим экран
            
            self.canvas.create_image(0, 0, anchor="nw", image=self.bg_photo)

        border_btn = tk.Button(btn_frame, text="Выделить границы", width=15, command=start_border_draw)
        border_btn.grid(row=0, column=0, padx=10, pady=5)
        Tooltip(border_btn, "ЛКМ - поставить метку. Соединять конечные точки не надо. Для появления маски нажать на кнопку сохранить.")
        save_btn = tk.Button(btn_frame, text="Сохранить", width=15, command=save_mask)
        save_btn.grid(row=0, column=1, padx=10, pady=5)
        Tooltip(save_btn, "Объеденяет все точки в одну маску")
        clear_btn = tk.Button(btn_frame, text="Стереть всё", width=15, command=clear_mask)
        clear_btn.grid(row=0, column=2, padx=10, pady=5)
        Tooltip(clear_btn, "Убирает все маски и точки на этой камере")
        back_btn = tk.Button(btn_frame, text="Назад", width=15, command=self.camera_window)
        back_btn.grid(row=0, column=3, padx=10, pady=5, sticky="w")

    def all_viol_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        columns = 4
        self.button_images = []
        self.orig_images = []

        button_size = 120
        padding = 5

        cameras_frame = tk.Frame(self.root)
        cameras_frame.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=85)
        self.root.rowconfigure(1, weight=15)
        self.root.columnconfigure(0, weight=1)

        # 🟡 ИЗМЕНЕНО: Отображаем реальные активные нарушения
        for i in range(len(self.active_violations)):
            row = i // columns
            col = i % columns
            
            # self.active_violations[i] содержит путь к файлу
            try:
                img = Image.open(self.active_violations[i])
                self.orig_images.append(img)
                photo = ImageTk.PhotoImage(img.resize((button_size, button_size)))
                self.button_images.append(photo)

                btn = tk.Button(
                    cameras_frame,
                    text=f"Нарушение {i + 1}",
                    image=photo,
                    compound="center",
                    fg="white",
                    font=("Arial", 12, "bold"),
                    bd=0,
                    highlightthickness=0,
                    command=lambda idx=i: self.violation_window(idx)
                )
                btn.grid(row=row, column=col, padx=padding, pady=padding, sticky="nsew")
                
                def resize_image(event, index=i, button=btn):
                    new_width = event.width
                    new_height = event.height
                    # Проверка индексов
                    if index < len(self.orig_images):
                        img_resized = ImageOps.fit(self.orig_images[index], (new_width, new_height), centering=(0.5, 0.5))
                        photo_new = ImageTk.PhotoImage(img_resized)
                        self.button_images[index] = photo_new
                        button.config(image=photo_new)

                btn.bind("<Configure>", resize_image)
                
            except Exception as e:
                print(f"Ошибка отображения нарушения {i}: {e}")

        for col in range(columns):
            cameras_frame.columnconfigure(col, weight=1)
        
        # Исправлен расчет строк (делим на columns)
        total_rows = (len(self.active_violations) + columns - 1) // columns if len(self.active_violations) > 0 else 1
        for row in range(total_rows):
            cameras_frame.rowconfigure(row, weight=1)

        bottom_frame = tk.Frame(self.root)
        bottom_frame.grid(row=1, column=0, sticky="nsew")
        bottom_frame.columnconfigure(0, weight=1)
        bottom_frame.rowconfigure(0, weight=1)

        back_btn = tk.Button(bottom_frame, text="Назад", width=20, command=self.main_window)
        back_btn.grid(row=0, column=0, pady=10)

    def violation_window(self, viol_index=0):
        for widget in self.root.winfo_children():
            widget.destroy()

        win_width = self.root.winfo_width() or 800
        win_height = self.root.winfo_height() or 600

        btn_height = int(win_height * 0.15)
        
        self.root.rowconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=0)
        self.root.columnconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=1)

        text_frame = ttk.Frame(self.root)
        text_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)

        log_text = tk.Text(
            text_frame,
            bg="#F0F0F0",
            fg="black",
            font=("Arial", 12),
            state="normal"
        )
        log_text.insert("end", self.violation_img[0])
        log_text.grid(row=0, column=0, sticky="nsew")

        photo_frame = ttk.Frame(self.root)
        photo_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        photo_frame.rowconfigure(0, weight=1)
        photo_frame.columnconfigure(0, weight=1)

        path = 'viol_detect'
        # 🟡 ИЗМЕНЕНО: Берем фото из списка активных
        if viol_index < len(self.active_violations):
            try:
                placeholder_img = Image.open(self.active_violations[viol_index])
                max_width = 1000

                img_w, img_h = placeholder_img.size
                crop_w = min(img_w, max_width)
                crop_h = img_h
                placeholder_img_cropped = placeholder_img.crop((0, 0, crop_w, crop_h))

                self.photo_image = ImageTk.PhotoImage(placeholder_img_cropped)
                photo_label = tk.Label(photo_frame, image=self.photo_image)
                photo_label.grid(row=0, column=0, sticky="nsew")
            except Exception as e:
                 print(f"Error loading viol img: {e}")

        btn_frame = ttk.Frame(self.root, height=btn_height)
        btn_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=5, padx=10)

        video_btn = ttk.Button(btn_frame, text=f"Посмотреть папку", command=lambda: self.open_folder(self.local_viol_dir))
        video_btn.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        Tooltip(video_btn, "Окрыть папку с фото")
        raport_btn = ttk.Button(btn_frame, text=f"Написать рапорт", command=lambda: self.violation_form_window(viol_index))
        raport_btn.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        Tooltip(raport_btn, "Написать подробный рапорт о нарушении")
        system_btn = ttk.Button(btn_frame, text=f"Ошибка системы", command=lambda: self.system_form_window(viol_index))
        system_btn.grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        Tooltip(system_btn, "Указать, где ошиблась система")
        back_btn = ttk.Button(btn_frame, text=f"Назад", command=self.all_viol_window)
        back_btn.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

    def open_folder(self, path):
        path = os.path.abspath(path)
        if not os.path.exists(path):
            print(f"Путь не существует: {path}")
            return

        system_name = platform.system()
        try:
            if system_name == "Windows":
                os.startfile(path)
            elif system_name == "Darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
        except Exception as e:
            print(f"Не удалось открыть папку: {e}")

    def violation_form_window(self, viol_index):
        for widget in self.root.winfo_children():
            widget.destroy()

        self.root.rowconfigure([0, 1, 2], weight=1)
        self.root.columnconfigure(0, weight=1)

        fio_frame = ttk.Frame(self.root)
        fio_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=10)
        ttk.Label(fio_frame, text="ФИО:").grid(row=0, column=0, sticky="w")
        fio_entry = ttk.Entry(fio_frame, width=50)
        fio_entry.grid(row=0, column=1, sticky="ew")

        violation_frame = ttk.Frame(self.root)
        violation_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
        ttk.Label(violation_frame, text="Суть нарушения:").grid(row=0, column=0, sticky="w")

        violation_options = ["нет каски", "нет жилета/куртки"]
        violation_var = tk.StringVar()
        violation_combo = ttk.Combobox(violation_frame, values=violation_options, textvariable=violation_var)
        violation_combo.grid(row=0, column=1, sticky="ew")
        violation_combo.set(violation_options[0])

        btn_frame = ttk.Frame(self.root)
        btn_frame.grid(row=2, column=0, pady=20)

        def save_form():
            fio_value = fio_entry.get()
            violation_value = violation_var.get()
            print(f"ФИО: {fio_value}, Нарушение: {violation_value}")

            if hasattr(self, "active_violations") and 0 <= viol_index < len(self.active_violations):
                self.active_violations.pop(viol_index)
                self.violation -=1

            self.violation_window(0) # Возврат к первому если есть

        save_btn = ttk.Button(btn_frame, text="Сохранить", command=save_form)
        save_btn.grid(row=0, column=0, padx=10)

        cancel_btn = ttk.Button(btn_frame, text="Отмена", command=self.violation_window)
        cancel_btn.grid(row=0, column=1, padx=10)

    def system_form_window(self, viol_index):
        for widget in self.root.winfo_children():
            widget.destroy()

        violation_frame = ttk.Frame(self.root)
        violation_frame.grid(row=0, column=0, padx=20, pady=20) # Fix layout
        ttk.Label(violation_frame, text="Суть ошибки:").grid(row=0, column=0)

        violation_options = ["нет человека, хотя система его видит",
                             "есть жилет/куртка, хотя система их не видит",
                             "есть каска, хотя система её не видит",
                             "система неправильно обрезает человека",
                             "другое"]
        violation_var = tk.StringVar()
        violation_combo = ttk.Combobox(violation_frame, values=violation_options, textvariable=violation_var)
        violation_combo.grid(row=0, column=1, sticky="ew")
        violation_combo.set(violation_options[0])

        btn_frame = ttk.Frame(self.root)
        btn_frame.grid(row=2, column=0, pady=20)

        def save_form():
            violation_value = violation_var.get()
            print(f"Ошибка: {violation_value}")

            if hasattr(self, "active_violations") and 0 <= viol_index < len(self.active_violations):
                self.active_violations.pop(viol_index)
                self.violation -=1

            self.violation_window(0)

        save_btn = ttk.Button(btn_frame, text="Сохранить", command=save_form)
        save_btn.grid(row=0, column=0, padx=10)

        cancel_btn = ttk.Button(btn_frame, text="Отмена", command=self.violation_window)
        cancel_btn.grid(row=0, column=1, padx=10)

    def create_input_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        title_label = ttk.Label(main_frame, text="Настройки",
                                font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))

        path_label = ttk.Label(main_frame, text="Путь к видео:")
        path_label.grid(row=1, column=0, sticky=tk.W, pady=5)

        self.path_entry = ttk.Entry(main_frame, width=50)
        self.path_entry.grid(row=1, column=1, padx=5, pady=5, sticky=(tk.W, tk.E))

        browse_btn = ttk.Button(main_frame, text="Обзор")
        browse_btn.grid(row=1, column=2, padx=5, pady=5)

        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=3, pady=20)

        self.process_btn = ttk.Button(button_frame, text="Сохранить")
        self.process_btn.pack(side=tk.LEFT, padx=5)

        self.active_btn = ttk.Button(button_frame, text="Назад", command=self.main_window)
        self.active_btn.pack(side=tk.LEFT, padx=5)

        main_frame.columnconfigure(1, weight=1)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

    # 🟡 ИЗМЕНЕНО: отображение живого видеопотока (размещение камер)
    def dispatch_frame(self, cam_id, image):
        """Вызывается из потока RabbitMQ для КАЖДОГО кадра любой камеры"""
        
        # 1. Обновляем СЕТКУ (Grid), если она открыта
        if cam_id in self.live_widgets:
            label_widget = self.live_widgets[cam_id]
            if label_widget.winfo_exists():
                self.update_label_image(label_widget, image, is_grid=True)

        # 2. Обновляем ДЕТАЛЬНОЕ ОКНО, если оно открыто для этой камеры
        if self.detail_window and self.detail_window.winfo_exists():
            if self.detail_cam_id == cam_id:
                self.update_label_image(self.detail_label, image, is_grid=False)

    def update_label_image(self, label_widget, image, is_grid):
        """Потокобезопасное обновление картинки в лейбле с правильным ресайзом"""
        try:
            # Получаем текущие размеры виджета
            # Если виджет еще не отрисован, берем дефолтные
            w = label_widget.winfo_width()
            h = label_widget.winfo_height()
            
            if w < 10: w = 300 if is_grid else 800
            if h < 10: h = 200 if is_grid else 600
            
            # 🟡 ИСПРАВЛЕНИЕ: Используем contain вместо fit
            # contain вмещает картинку полностью, сохраняя пропорции (добавляет пустые поля если надо)
            # fit обрезает края (crop)
            image_resized = ImageOps.contain(image, (w, h))
            
            photo = ImageTk.PhotoImage(image_resized)
            
            def _update():
                if label_widget.winfo_exists():
                    label_widget.configure(image=photo)
                    label_widget.image = photo # Удерживаем ссылку
            
            self.root.after(0, _update)
        except:
            pass

def main():
    root = tk.Tk()
    style = ttk.Style()
    style.configure("Flat.TButton", relief="flat", borderwidth=0, padding=10)
    app = VideoProcessorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()