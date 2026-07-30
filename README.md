# PPE Video Analytics and Safety Monitoring System

A proof-of-concept system for monitoring PPE compliance in video streams from industrial sites. It detects people, checks helmet and safety-vest presence, evaluates whether a person is inside a configured safety zone, and sends violation alerts to a dispatcher client.

> This repository is an archived R&D proof of concept. It demonstrates the architecture and the implemented processing pipeline; it is not presented as a production-ready safety system.

## Application area

The project targets high-risk environments such as construction sites, ports, and factories where operators need to review video streams and be notified about potential PPE violations.

A typical workflow is:

1. An operator registers an RTSP stream, webcam index, or local video file through the API.
2. The Ingestor reads frames and publishes them to RabbitMQ.
3. The Processor detects and tracks people, evaluates PPE and zone conditions, then publishes preview frames and alerts.
4. The desktop client displays camera previews and received violation evidence.

## Features

- Camera registration and safety-zone management through a FastAPI REST API
- Video ingestion from RTSP sources, local video files, or numeric webcam indexes supported by OpenCV
- RabbitMQ-based asynchronous delivery of source frames, processed previews, and violation alerts
- Person detection and tracking using Ultralytics YOLO with ByteTrack
- Helmet and vest detection using locally mounted ONNX models when they are available
- Fallback PPE detections based on COCO classes from the person model when a dedicated ONNX PPE model is unavailable
- Polygonal safety zones stored in PostgreSQL as JSON coordinates
- Temporal filtering of PPE violations to reduce alerts from isolated frame-level detections
- Evidence snapshots saved to a shared directory and served by the API
- Tkinter dispatcher client for managing cameras and zones, viewing processed streams, and reviewing received alerts

## Architecture

The application consists of four components orchestrated by Docker Compose:

```text
                         ┌─────────────────┐
                         │   PostgreSQL    │
                         │ cameras, zones  │
                         └────────┬────────┘
                                  │
                                  │ reads active cameras
                                  │
┌──────────────┐  raw frames  ┌───▼───────┐  processed frames  ┌────────────────┐
│   Ingestor   ├─────────────►│ RabbitMQ  ├───────────────────►│ Desktop client │
│ OpenCV/FFmpeg│              │           │                    │   (Tkinter)    │
└──────▲───────┘              └───┬───────┘                    └────────────────┘
       │                          │ alerts
       │                          │
┌──────┴───────┐             ┌────▼────────┐
│ Video source │             │  Processor  │
│ RTSP / file  │             │ YOLO, ONNX, │
└──────────────┘             │ Shapely     │
                              └────┬────────┘
                                   │ zone requests and snapshots
                              ┌────▼────────┐
                              │ API Server  │
                              │   FastAPI   │
                              └─────────────┘
```

### Components

| Component | Responsibility |
|---|---|
| `db` | PostgreSQL database for cameras, zones, and violation-event schema |
| `rabbitmq` | Broker for raw frames, processed preview frames, and violation alerts |
| `api_server` | FastAPI service that manages cameras and zones and serves evidence snapshots from `/static` |
| `ingestor` | Polls active cameras from PostgreSQL, captures video frames, resizes them, and publishes JPEG payloads to RabbitMQ |
| `processor` | Consumes raw frames, runs detection and tracking, checks PPE and zones, saves evidence, publishes alerts, and sends annotated preview frames |
| `main.py` | Standalone Tkinter dispatcher client; connects to the API and RabbitMQ outside Docker |

### Data flow

1. The API server creates the PostgreSQL tables at startup.
2. The dispatcher client or an HTTP client creates active cameras and polygonal zones through the API.
3. The Ingestor polls active cameras, reads a frame, resizes it to the configured width, JPEG-encodes it, and publishes it to `raw_frames_queue`.
4. The Processor consumes frames from `raw_frames_queue`, retrieves zones from the API, and runs person tracking and PPE detection.
5. For each tracked person whose lower bounding-box center is inside a zone, `ViolationManager` evaluates PPE status over a time window.
6. When the configured temporal condition is met, the Processor writes an annotated evidence image to `event_data`, publishes an alert to `violation_alerts_queue`, and sends the processed frame to `processed_stream_queue`.
7. The desktop client consumes alerts and processed preview frames from RabbitMQ.

## Detection pipeline

The Processor loads the following local model paths from the `models` directory mounted into the container:

```text
models/
├── yolov8n.pt
├── helmet_detector/
│   └── 1/
│       └── model.onnx
└── vest_detector/
    └── 1/
        └── model.onnx
```

`yolov8n.pt` is used for person detection and ByteTrack-based tracking. Dedicated helmet and vest ONNX models are loaded when their files are available. If either PPE model is absent, the Processor falls back to classes from the COCO model; this fallback is intended only to keep the demonstration pipeline running and should not be treated as equivalent to a dedicated PPE model.

### Processed-frame annotations

The Processor annotates people in preview frames and saved evidence images.

| Annotation | Meaning |
|---|---|
| `NoH` | Helmet was not detected for the tracked person in the current frame |
| `NoV` | Safety vest was not detected for the tracked person in the current frame |
| Green bounding box | The tracked person has both a detected helmet and safety vest |
| Yellow bounding box | One PPE item was not detected: either `NoH` or `NoV` |
| Red bounding box | Neither a helmet nor a safety vest was detected: both `NoH` and `NoV` |

The labels and colours describe frame-level detection results. A violation alert is emitted only after the temporal filtering logic evaluates a tracked person inside a configured safety zone.

## Repository structure

```text
.
├── .env.example
├── docker-compose.yml
├── main.py                         # Tkinter dispatcher client
├── requirements.txt                # Desktop-client dependencies
├── media/                          # Local test videos, not tracked by Git
├── models/                         # Local YOLO and ONNX model files
└── services/
    ├── api_server/
    │   ├── main.py                 # FastAPI endpoints and application lifecycle
    │   ├── models.py               # SQLAlchemy ORM models
    │   ├── schemas.py              # Pydantic API DTOs
    │   ├── database.py             # Async database engine and sessions
    │   ├── config.py               # API settings
    │   ├── requirements.txt
    │   └── Dockerfile
    ├── ingestor/
    │   ├── main.py                 # Camera polling and stream lifecycle
    │   ├── video_stream.py         # OpenCV capture and RabbitMQ publishing
    │   ├── db_client.py            # Active-camera database query
    │   ├── config.py               # Ingestor settings
    │   ├── requirements.txt
    │   └── Dockerfile
    └── processor/
        ├── main.py                 # Frame consumer and alert publishing
        ├── logic.py                # Zone and temporal violation logic
        ├── tracker.py              # Standalone IoU tracker utility
        ├── config.py               # Processor settings
        ├── inference/
        │   └── detector.py         # YOLO and ONNX model integration
        ├── requirements.txt
        └── Dockerfile
```

## Requirements

- Docker Desktop with Linux containers enabled
- Docker Compose v2
- Python 3.10 or newer for the standalone desktop client
- Local model files in `models/`
- A video source accessible to the Ingestor: RTSP URL, webcam index, or video file in `media/`

The Docker services use PostgreSQL 15 and RabbitMQ 3.11 with the management plugin.

## Installation

Clone the repository and open its root directory:

```powershell
git clone https://github.com/DevDynastyOfProgrammers/PPE-Analytics.git
cd PPE-Analytics
```

Create a local environment file:

```powershell
Copy-Item .env.example .env
```

Create and prepare a virtual environment for the desktop client:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Configuration

The Compose services read environment variables from `.env`.

```env
POSTGRES_DB=ppe_violations_db
POSTGRES_USER=admin
POSTGRES_PASSWORD=your_password

RABBITMQ_DEFAULT_USER=guest
RABBITMQ_DEFAULT_PASS=guest

API_SERVER_PORT=8888
RABBITMQ_MANAGEMENT_PORT=15672
```

Do not commit `.env`. Use a non-default database password outside a local demonstration environment.

### Video source

For a reproducible local run, place a video file in `media/`, for example:

```text
media/test_video.mp4
```

The directory is mounted in the Ingestor container as `/app/media`. Register the camera with this container path, not with a Windows host path.

The Ingestor resizes frames to a width of 640 pixels before publishing them. Zone coordinates must therefore be created for the resized preview-frame coordinate system.

## Run

Start all Docker services:

```powershell
docker compose up -d --build
```

Check container status:

```powershell
docker compose ps
```

Expected state:

- `db` and `rabbitmq` are `healthy`
- `api_server`, `ingestor`, and `processor` are running

The API is available at:

```text
http://localhost:8888
```

RabbitMQ Management UI is available at:

```text
http://localhost:15672
```

Start the dispatcher client in a separate PowerShell window:

```powershell
.\.venv\Scripts\Activate.ps1
python .\main.py
```

## Smoke test

### 1. Verify the API

```powershell
Invoke-RestMethod http://localhost:8888/cameras/
```

Expected result: a JSON array, initially usually `[]`.

### 2. Register a local test video

Place a file at `media/test_video.mp4`, then run:

```powershell
$cameraPayload = @{
    name = "Local test video"
    rtsp_url = "/app/media/test_video.mp4"
    is_active = $true
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8888/cameras/" `
    -ContentType "application/json" `
    -Body $cameraPayload
```

The Ingestor polls the camera list every 10 seconds. Wait for the next poll cycle, then inspect its logs:

```powershell
docker compose logs --tail=80 ingestor
```

Expected log fragment:

```text
[Cam <camera_id>] STARTED. Source: /app/media/test_video.mp4
[Cam <camera_id>] Connected to RabbitMQ
```

### 3. Create a safety zone

First obtain the created camera identifier:

```powershell
Invoke-RestMethod http://localhost:8888/cameras/
```

Use the preview image at the following URL to choose coordinates for the resized frame:

```text
http://localhost:8888/static/previews/cam_<camera_id>.jpg
```

Create a polygon with at least three points. Replace `<camera_id>` and the example points with coordinates suitable for the preview image:

```powershell
$zonePayload = @{
    camera_id = <camera_id>
    name = "Test zone"
    polygon_coordinates = @(
        @(10, 10),
        @(630, 10),
        @(630, 400),
        @(10, 400)
    )
} | ConvertTo-Json -Depth 4

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8888/zones/" `
    -ContentType "application/json" `
    -Body $zonePayload
```

Verify the zone:

```powershell
Invoke-RestMethod http://localhost:8888/cameras/<camera_id>/zones
```

### 4. Observe processing

Open the desktop client, select **Начать**, then open **LIVE Просмотр**. If the input video contains people and a configured zone, the client should display processed preview frames.

Inspect service logs:

```powershell
docker compose logs --tail=100 ingestor processor
```

Expected Processor startup log:

```text
[*] Waiting for frames...
```

When a temporal PPE violation is detected, the Processor logs an alert and publishes a message to `violation_alerts_queue`. Evidence images are saved in `event_data/<YYYY-MM-DD>/` and available through the API under `/static/<YYYY-MM-DD>/`.

## Tests

Run the Processor unit tests inside its Docker image:

```powershell
docker compose run --rm processor python -m unittest discover -s tests -v
```

The tests cover temporal PPE-violation filtering and polygonal zone checks. They do not require PostgreSQL, RabbitMQ, a video source, or loaded model weights.

## Demonstration materials

No generated screenshots, GIFs, or videos are included in this repository. Before portfolio review, add only real materials captured from your own run.

Recommended materials:

1. **Architecture diagram** — export the diagram from this README or create an equivalent diagram based on the running components.
2. **API screenshot** — open `http://localhost:8888/docs` after starting the stack and capture the FastAPI interactive documentation.
3. **RabbitMQ screenshot** — open `http://localhost:15672`, navigate to Queues, and capture the queues created by the running pipeline.
4. **Dispatcher screenshot** — configure a local test video and safety zone, then capture the `LIVE Просмотр` window with an annotated frame.
5. **Evidence screenshot** — capture an actual violation snapshot served under `/static/...` together with the corresponding Processor log entry.

Store small documentation images in a tracked directory such as `docs/images/` and reference them from this README. Do not commit private videos, RTSP credentials, personal data, model weights without redistribution rights, or generated event data.

## Limitations

- The project is an archived PoC, not a production-ready safety-monitoring system.
- The repository does not contain a completed Triton inference-server integration.
- Detection quality, FPS, latency, and reliability have not been benchmarked or reported in this repository.
- The fallback PPE mode uses COCO classes when dedicated ONNX PPE models are unavailable; it is intended for pipeline continuity rather than validated PPE recognition.
- The Ingestor requires the video source to be reachable from inside its container.
- The current implementation assumes a local Docker Compose network and RabbitMQ access from the desktop client.
- Camera and zone persistence is managed through SQLAlchemy table creation at application startup; database schema migrations are not implemented.
- Model weights and test media may be local assets and must be prepared before a full demonstration run.
- Unit tests currently cover only the Processor's temporal violation logic and polygonal zone checks; integration tests for the Docker services and model inference are not included.

## Personal contribution

My contribution to this team project focused on the backend and ML-processing infrastructure:

- Implemented the Docker Compose-based microservice architecture
- Implemented the Ingestor service for video-source capture and asynchronous frame delivery
- Implemented the Processor integration layer for detection models and post-processing of their results
- Implemented PPE and geo-zone violation-processing flow, including temporal filtering and evidence generation
- Implemented the API server integration used by the dispatcher client for remote camera and zone management
- Integrated the backend services with the dispatcher client data flows

The Tkinter desktop client interface was developed by a teammate.

## Stop services

Stop containers while preserving PostgreSQL and RabbitMQ volumes:

```powershell
docker compose down
```

Remove containers and persistent service volumes:

```powershell
docker compose down -v
```

After `docker compose down -v`, register cameras and zones again because the database data will be removed.