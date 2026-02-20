# 👷‍♂️ PPE Video Analytics & Safety Monitoring System (PoC)

![Status](https://img.shields.io/badge/Status-Archived--PoC-red)
![Tech](https://img.shields.io/badge/Stack-Python%20|%20Docker%20|%20YOLOv8%20|%20RabbitMQ-blue)

> **Note:** This project is an R&D **Proof of Concept (PoC)** developed to explore distributed microservice architectures, hybrid CV tracking, and real-time event processing in constrained environments. It is currently archived as a successful technology demonstration.

## 📌 Project Overview
The system is designed for automated safety compliance monitoring in high-risk industrial environments (ports, construction sites, factories). It analyzes real-time video streams to detect employees, verify Personal Protective Equipment (PPE) compliance (Helmets and Safety Vests), and monitor intrusion into hazardous geo-fenced zones.

### Core Features:
* **Hybrid Object Detection:** Tracking-assisted detection to minimize flickering and false positives.
* **Geo-Fencing:** User-defined polygonal "Danger Zones" stored in a spatial database.
* **Temporal Logic (Debouncing):** Alert generation based on a threshold (e.g., PPE missing for >50% of frames over a 3-second window).
* **CPU Optimized:** Tailored for deployment in air-gapped environments without high-end GPU acceleration (leveraging OpenVINO/ONNX).

## 🏗 System Architecture
The system follows a modular microservices pattern orchestrated via **Docker Compose**:

1. **Ingestor (Video Acquisition):**
   * High-performance frame capture using OpenCV/FFmpeg.
   * Frame normalization, resizing, and asynchronous publishing to the message broker.
2. **Processor (CV Engine):**
   * **Person Detection & Tracking:** YOLOv8 + ByteTrack.
   * **PPE Analysis:** Specialized ONNX models for high-speed CPU inference.
   * **Spatial Logic:** Geometric intersection checks (Shapely) against database-defined polygons.
   * **State Management:** Accumulates statistics per object ID to trigger high-fidelity alerts.
3. **API Server (FastAPI):**
   * Centralized management of cameras and safety zones.
   * Static asset serving for violation evidence (snapshots).
   * Asynchronous DB interactions using SQLAlchemy.
4. **Client App (Desktop UI):**
   * Tkinter-based dashboard for dispatchers.
   * Live-stream visualization via a dedicated RabbitMQ processed-frame queue.
   * Interactive polygon editor for safety zone configuration.

## 🛠 Tech Stack
* **Language:** Python 3.10
* **Computer Vision:** Ultralytics (YOLOv8), OpenCV, ByteTrack, ONNXRuntime.
* **Backend:** FastAPI, SQLAlchemy (Async), Pydantic.
* **Messaging:** RabbitMQ (Asynchronous frame and alert distribution).
* **Database:** PostgreSQL.
* **DevOps:** Docker, Docker Compose (CPU-optimized builds).

## 🚀 Engineering Challenges & Solutions
* **Hardware Constraints:** Developed a custom CPU-optimized pipeline using specialized PyTorch builds, reducing the need for NVIDIA GPUs in edge deployments.
* **Network Reliability:** Implemented a "Fire-and-Forget" frame ingestor pattern with RabbitMQ to decouple video capture from heavy ML inference, preventing video lag during peak processing.
* **False Positive Mitigation:** Instead of frame-by-frame alerting, a temporal analysis window was implemented. An alert is only triggered if an object (tracked by ID) violates rules for a significant percentage of its visible lifespan.

## 📂 Repository Structure
```text
├── services/
│   ├── api_server/    # FastAPI REST service & DB models
│   ├── ingestor/      # Video stream acquisition & RabbitMQ producer
│   └── processor/     # ML Core, logic, and visualization engine
├── models/            # Placeholder for YOLO/ONNX weights (local-only)
├── event_data/        # Shared volume for violation snapshots
├── main3.py           # Tkinter Desktop Client
└── docker-compose.yml # Infrastructure orchestration