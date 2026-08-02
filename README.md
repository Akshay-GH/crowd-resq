# CrowdResQ Control

![Next.js](https://img.shields.io/badge/Next.js-15-black?logo=nextdotjs)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=111111)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3-38B2AC?logo=tailwindcss&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-5C3EE8?logo=opencv&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB-47A248?logo=mongodb&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)

CrowdResQ is a local AI-assisted event crowd monitoring system. It reads a fixed live camera feed, detects and tracks people, estimates density and movement risk, and alerts the event authority when stampede risk becomes high.

## Architecture

CrowdResQ is split into a Next.js control-room frontend and a FastAPI crowd-risk backend. The browser uses Next.js API routes for authority sign-up, sign-in, logout, and current-user checks, while the protected dashboard talks directly to the FastAPI service for camera control, scene setup, MJPEG video streams, alerts, and live risk updates over WebSocket. The backend starts a camera worker that reads frames with OpenCV, runs YOLO person detection/tracking, maps detections through the saved scene configuration, calculates risk scores, and writes high-risk alerts to local JSON storage. User accounts live in MongoDB through Mongoose, while scene calibration and alert history are stored in backend JSON files.

```mermaid
flowchart TD
  subgraph Client["Client"]
    Browser["Browser UI<br/>Next.js pages"]
    Dashboard["Control dashboard<br/>/dashboard/control"]
  end

  subgraph Frontend["Frontend: Next.js"]
    AuthAPI["Auth API routes<br/>/api/auth/*"]
    AuthLib["JWT auth helper<br/>auth-token cookie"]
    UserModel["Mongoose User model"]
  end

  subgraph Backend["Backend: FastAPI"]
    FastAPI["FastAPI app<br/>backend/app.py"]
    CameraWorker["CameraWorker<br/>capture, detect, stream"]
    RiskEngine["RiskEngine<br/>risk scoring"]
    SceneStore["SceneConfigStore"]
    AlertManager["AlertManager"]
  end

  subgraph Stores["Data Stores"]
    MongoDB[("MongoDB<br/>users")]
    SceneJSON[("backend/data/scene_config.json")]
    AlertsJSON[("backend/data/alerts.json")]
  end

  subgraph External["External Inputs / Services"]
    Camera[["Camera source<br/>index or stream URL"]]
    YOLO[["YOLO model weights<br/>CROWD_MODEL"]]
  end

  Browser -->|"POST /api/auth/signup, POST /api/auth/signin"| AuthAPI
  Browser -->|"GET /api/auth/me, POST /api/auth/logout"| AuthAPI
  AuthAPI -->|"connectDB(), User.findOne(), user.save()"| UserModel
  UserModel -->|"mongoose documents"| MongoDB
  AuthAPI -->|"generate/read/clear auth-token"| AuthLib

  Browser -->|"protected page"| Dashboard
  Dashboard -->|"GET /health, POST /start, POST /stop"| FastAPI
  Dashboard -->|"GET/POST /scene/config"| FastAPI
  Dashboard -->|"GET /alerts, POST /alerts/{id}/ack"| FastAPI
  Dashboard -->|"GET /stream/raw.mjpg, GET /stream/processed.mjpg"| FastAPI
  Dashboard -->|"WS /ws/risk"| FastAPI

  FastAPI -->|"start(), stop(), latest_risk(), latest_jpeg()"| CameraWorker
  FastAPI -->|"load(), update()"| SceneStore
  FastAPI -->|"list_alerts(), acknowledge()"| AlertManager
  CameraWorker -->|"cv2.VideoCapture frames"| Camera
  CameraWorker -->|"YOLO.track(), YOLO.predict()"| YOLO
  CameraWorker -->|"people detections + scene config"| RiskEngine
  CameraWorker -->|"load scene points"| SceneStore
  CameraWorker -->|"create_alert(risk)"| AlertManager
  SceneStore -->|"read/write calibration, entry, exit, thresholds"| SceneJSON
  AlertManager -->|"read/write alert history"| AlertsJSON
```

**Notes**

- No unverified edges are shown; each connection is backed by an opened source file, import, route handler, or explicit `fetch`/WebSocket call.
- Discovery covered project source/config/data files under `backend/`, `frontend/`, and root docs; generated dependency/build folders (`backend/venv/`, `frontend/node_modules/`, `frontend/.next/`) and binary demo assets were skipped.

**Screenshots**

![Signin](demo/signin.png)
![Signup](demo/signup.png)

## 🎥 Demo

▶ **Full Demo:** [click](https://drive.google.com/file/d/1yS_lbw1Yu-MHLP7pKeL1BIItW2d-gjw7/view?usp=sharing)

## Tech Used

| Area | Tech |
| --- | --- |
| Frontend app | Next.js App Router, React, TypeScript |
| UI | Tailwind CSS, shadcn/ui-style components, Radix UI primitives, lucide-react, Recharts |
| Frontend API/auth | Next.js API routes, JWT, HTTP-only auth cookie, bcryptjs |
| User storage | MongoDB through Mongoose |
| Backend API | FastAPI, Uvicorn, Pydantic, CORS middleware, WebSocket, MJPEG streaming |
| Computer vision | OpenCV, Ultralytics YOLO, NumPy |
| Backend storage | JSON files for scene configuration and alert history |
| Configuration | `frontend/.env`, backend environment variables such as `CROWD_MODEL`, `CAMERA_SOURCE`, `CROWD_CONF`, `CROWD_IOU`, and `CROWD_IMGSZ` |

## Local Testing

See [HOW_TO_RUN.md](HOW_TO_RUN.md) for exact setup and testing steps.
