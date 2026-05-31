# CrowdResQ Backend

Local FastAPI service for live crowd-risk monitoring from one fixed camera.

## Run

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

## Core Flow

1. `POST /start` opens the camera source.
2. The camera worker reads frames continuously.
3. YOLO detects and tracks people.
4. Person foot points are mapped into the calibrated ground plane.
5. The risk engine calculates density, congestion, flow, exit load, and growth.
6. High or critical risk creates an automatic alert.
7. The frontend consumes MJPEG video and JSON/WebSocket risk updates.

## Main Endpoints

- `GET /health`
- `POST /start`
- `POST /stop`
- `GET /latest`
- `GET /stream/raw.mjpg`
- `GET /stream/processed.mjpg`
- `GET /scene/config`
- `POST /scene/config`
- `POST /scene/calibration`
- `POST /scene/entry-points`
- `POST /scene/exit-points`
- `GET /alerts`
- `POST /alerts/{alert_id}/ack`
- `WS /ws/risk`

## Scene Setup

The dashboard should send 4 calibration points from the live image:

```json
[
  { "id": "p1", "label": "Top Left", "x": 120, "y": 180 },
  { "id": "p2", "label": "Top Right", "x": 910, "y": 175 },
  { "id": "p3", "label": "Bottom Right", "x": 1120, "y": 690 },
  { "id": "p4", "label": "Bottom Left", "x": 80, "y": 700 }
]
```

Entry and exit points use the same image-coordinate format.
