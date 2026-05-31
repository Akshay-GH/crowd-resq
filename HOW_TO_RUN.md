# CrowdResQ Local Test Guide

## Prerequisites

- Node.js 18+
- Python 3.10 or 3.11
- MongoDB connection string, local or Atlas
- A webcam or fixed USB/IP camera available to OpenCV

## 1. Backend Setup

Open a terminal:

```powershell
cd D:\resumes\projects\crowd-resq\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

If you already installed dependencies before this project update, run this once:

```powershell
pip install -r requirements.txt
```

This installs the WebSocket support needed by `/ws/risk`.

The backend uses `yolo26n.pt` by default. The first detection run may download the model once through Ultralytics. To choose another compatible Ultralytics model, set `CROWD_MODEL` before starting the backend:

```powershell
$env:CROWD_MODEL="yolo11n.pt"
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Check the backend:

```text
http://localhost:8000/health
http://localhost:8000/docs
```

Expected `/health` before starting the camera:

```json
{
  "ok": true,
  "running": false
}
```

## 2. Frontend Setup

Open a second terminal:

```powershell
cd D:\resumes\projects\crowd-resq\frontend
npm install
```

Create `frontend/.env`:

```env
DB_URL=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/crowdResqDB
JWT_SECRET=change-this-secret
NEXT_PUBLIC_CROWD_API=http://localhost:8000
```

If you open the frontend through your LAN IP, use the backend LAN URL too:

```env
NEXT_PUBLIC_CROWD_API=http://192.168.43.31:8000
```

Start the frontend:

```powershell
npm.cmd run dev
```

Open:

```text
http://localhost:3000
```

## 3. Test The App

1. Open `http://localhost:3000/signup`.
2. Create an authority account.
3. Sign in.
4. You should land on `http://localhost:3000/dashboard/control`.
5. Enter a camera source in the processed feed panel.
   - Laptop webcam: `0`
   - Second/virtual camera: `1`
   - IP camera stream URL: `http://PHONE_IP:PORT/video`
6. Press **Start** in the processed feed panel.
7. The raw and processed feeds should appear.

## 3A. Use Iriun Phone Camera

Iriun works by turning your phone into a virtual webcam on your laptop.

1. Install **Iriun Webcam** on your phone.
2. Install **Iriun Webcam for Windows** on your laptop.
3. Connect phone and laptop to the same Wi-Fi/hotspot.
4. Open Iriun on the phone.
5. Open Iriun on the laptop and wait until it shows the phone camera preview.
6. Start the CrowdResQ backend and frontend.
7. In the dashboard camera source field, try:
   - `0`
   - if that opens the laptop webcam instead, press **Stop**, enter `1`, then press **Start**
   - if needed, repeat with `2`

OpenCV camera indexes depend on your laptop, so Iriun may be `0`, `1`, or `2`.

If Iriun does not appear:

1. Close Zoom/Meet/Teams/Camera app.
2. Restart the Iriun phone app and Windows app.
3. Restart the FastAPI backend.
4. Open `http://localhost:8000/cameras/probe` to see which OpenCV camera indexes are available.
5. Try an available `source` value from the probe result.

Example probe result:

```json
{
  "items": [
    { "source": 0, "available": false, "backend": "unavailable" },
    { "source": 1, "available": true, "backend": "dshow", "width": 1280, "height": 720 }
  ]
}
```

In this example, use `1` in the dashboard camera source field.

## 4. Configure The Scene

Use the raw feed panel:

1. Select **Calibration**.
2. Click 4 floor corners around the monitored event-ground area.
3. Select **Entry** and click one or more entry points.
4. Select **Exit** and click one or more exit points.
5. The backend saves these points in `backend/data/scene_config.json`.

## 5. Verify Risk And Alerts

Watch the right side of the dashboard:

- `Stampede Risk`
- `People`
- `Max density`
- `Avg speed`
- `Exit Status`
- `Risk Trend`
- `Automatic Alerts`

Alerts are generated when the backend risk level reaches `HIGH` or `CRITICAL`.

## Useful Backend Endpoints

```text
GET  /health
GET  /cameras/probe
POST /start
POST /stop
GET  /latest
GET  /stream/raw.mjpg
GET  /stream/processed.mjpg
GET  /scene/config
POST /scene/config
GET  /alerts
WS   /ws/risk
```

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Backend not reachable | Make sure Uvicorn is running on port 8000 |
| CORS error from LAN IP | Restart the backend after pulling this change, and set `NEXT_PUBLIC_CROWD_API` to your machine IP, for example `http://192.168.43.31:8000` |
| Frontend cannot sign in | Check `DB_URL` and `JWT_SECRET` in `frontend/.env` |
| Camera does not start | Close other apps using the webcam |
| `Unsupported upgrade request` for WebSocket | Run `pip install -r requirements.txt`, then restart the backend |
| Old YOLOv5 compatibility error | The backend no longer uses `backend/yolov5s.pt`; restart the backend and let Ultralytics use `yolo26n.pt`, or set `CROWD_MODEL` to another compatible model |
| PowerShell blocks npm | Use `npm.cmd run dev` instead of `npm run dev` |
| Port already in use | Stop the old process or use another port |
