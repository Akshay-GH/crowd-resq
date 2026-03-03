# CROWD-RESQ

A real-time crowd monitoring and emergency response system for campus environments. It combines **AI-powered video surveillance** (YOLOv5 detection, heatmaps, A\* pathfinding) with **role-based dashboards** for students, security guards, and ambulance services.

---

## Features

- **Live Crowd Detection** — YOLOv5 object detection on camera/video feeds with density heatmaps
- **Evacuation Pathfinding** — A\* algorithm computes optimal evacuation routes overlaid on the video feed
- **Role-Based Dashboards** — Tailored UI for Students (alerts & messaging), Security Guards (raw + AI feeds, crowd stats), and Ambulance Services (processed feed with evacuation paths)
- **Authentication** — JWT-based auth with HTTP-only cookies and role-based route protection
- **Real-Time Streaming** — FastAPI MJPEG server streams raw and AI-processed video to the frontend

---

## Tech Stack

| Layer    | Technologies                                              |
| -------- | --------------------------------------------------------- |
| Frontend | Next.js 15, React 18, TypeScript, Tailwind CSS, shadcn/ui |
| Backend  | FastAPI, Uvicorn, OpenCV, Ultralytics YOLOv5, NumPy       |
| Database | MongoDB (Mongoose)                                        |
| Auth     | JSON Web Tokens (HTTP-only cookies)                       |

---

## Project Structure

```
crowd-resq-project/
├── frontend/                           # Next.js frontend (port 3000)
│   ├── app/
│   │   ├── api/auth/                   # Auth API routes (signup, signin, logout, me)
│   │   ├── dashboard/
│   │   │   ├── student/                # Student dashboard
│   │   │   ├── SecurityGuard/          # Security guard dashboard
│   │   │   └── ambulance/              # Ambulance dashboard
│   │   └── page.tsx                    # Landing page
│   ├── lib/                            # DB connection, auth helpers, models
│   └── components/                     # UI components (shadcn/ui)
│
├── backend/
│   ├── app.py                          # FastAPI MJPEG streaming server
│   ├── y_h_A.py                        # YOLO + Heatmap + A* processor
│   └── yolov5s.pt                      # YOLOv5 model weights
│
└── HOW_TO_RUN.md                       # Detailed setup guide
```

---

## Prerequisites

- **Node.js** 18+
- **Python** 3.10–3.11
- **MongoDB** (Atlas or local)

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/Akshay-GH/CROWD-RESQ.git
cd CROWD-RESQ
```

### 2. Frontend

```bash
cd frontend
npm install
```

Create a `.env` file:

```env
DB_URL=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/crowdResqDB
JWT_SECRET=your-secret-key
```

```bash
npm run dev
```

Frontend runs at **http://localhost:3000**.

### 3. Backend (FastAPI)

```bash
cd backend
python -m venv venv
# Windows: .\venv\Scripts\Activate.ps1
# macOS/Linux: source venv/bin/activate
pip install fastapi uvicorn python-multipart ultralytics opencv-python numpy
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

API runs at **http://localhost:8000** &nbsp;|&nbsp; Swagger docs at **/docs**.

### 4. YOLO Processor

In a separate terminal (same venv):

```bash
cd backend
python y_h_A.py
```

Follow the prompts to select a video source and calibrate ground points.

---

## Usage

| Dashboard      | URL                                           | Purpose                              |
| -------------- | --------------------------------------------- | ------------------------------------ |
| Landing        | http://localhost:3000                         | Sign in / Sign up                    |
| Student        | http://localhost:3000/dashboard/student       | Emergency alerts & messaging         |
| Security Guard | http://localhost:3000/dashboard/SecurityGuard | Live raw + AI video feeds, stats     |
| Ambulance      | http://localhost:3000/dashboard/ambulance     | AI feed with evacuation path overlay |

---

## How It Works

1. **y_h_A.py** captures video, runs YOLOv5 detection, generates heatmaps, computes A\* evacuation paths, and writes processed frames to shared JPG files.
2. **app.py** (FastAPI) reads those shared JPGs and serves them as MJPEG streams over HTTP.
3. **Next.js dashboards** display the streams via `<img>` tags pointed at the MJPEG endpoints, with role-appropriate controls and information.

---

## License

This project is for educational purposes.

---

> See [HOW_TO_RUN.md](HOW_TO_RUN.md) for the full step-by-step setup guide and troubleshooting tips.
