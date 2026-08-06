import asyncio
import os
import time
from typing import Any, Dict, List, Optional, Union

import jwt
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from core.alert_manager import AlertManager
from core.camera_worker import CameraWorker
from core.scene_config import SceneConfigStore


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    load_dotenv(os.path.join(BASE_DIR, "..", "frontend", ".env"))
except ImportError:
    pass

DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_NAME = os.getenv("CROWD_MODEL", "yolo26n.pt")
DEFAULT_CAMERA_SOURCE = os.getenv("CAMERA_SOURCE", "0")
JWT_SECRET = os.getenv("JWT_SECRET", "fallback-secret-change-me")

scene_store = SceneConfigStore(os.path.join(DATA_DIR, "scene_config.json"))
alert_manager = AlertManager(os.path.join(DATA_DIR, "alerts.json"))
camera_worker = CameraWorker(scene_store, alert_manager, MODEL_NAME)

security_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    token: Optional[str] = Query(None),
) -> Dict[str, Any]:
    raw_token = credentials.credentials if credentials else token
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
        )
    try:
        payload = jwt.decode(raw_token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )


app = FastAPI(title="CrowdResQ Stampede Risk Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://crowdresq-controlroom.vercel.app",
    ],
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Point(BaseModel):
    id: Optional[str] = None
    label: Optional[str] = None
    x: float
    y: float


class SceneConfigBody(BaseModel):
    calibration_points: Optional[List[Point]] = None
    entry_points: Optional[List[Point]] = None
    exit_points: Optional[List[Point]] = None
    risk_thresholds: Optional[Dict[str, int]] = None


class StartBody(BaseModel):
    source: Optional[Union[int, str]] = None


def _normalize_camera_source(source: Optional[Union[int, str]]) -> Union[int, str]:
    selected_source: Union[int, str] = source if source is not None else DEFAULT_CAMERA_SOURCE
    if isinstance(selected_source, str) and selected_source.strip().isdigit():
        return int(selected_source)
    return selected_source


def _point_dict(point: Point) -> Dict[str, Any]:
    if hasattr(point, "model_dump"):
        return point.model_dump(exclude_none=True)
    return point.dict(exclude_none=True)


def _mjpeg_generator(processed: bool = True):
    boundary = "frame"
    idle_cycles = 0
    while True:
        if not camera_worker.running:
            idle_cycles += 1
            if idle_cycles > 30:  # Exit stream after ~3s when camera is stopped
                break
            time.sleep(0.1)
            continue

        frame = camera_worker.latest_jpeg(processed=processed)
        if frame is None:
            time.sleep(0.05)
            continue

        idle_cycles = 0
        yield (
            b"--" + boundary.encode() + b"\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n"
            + frame
            + b"\r\n"
        )
        time.sleep(0.03)


@app.get("/health")
def health():
    return {
        "ok": True,
        "running": camera_worker.running,
        "model": MODEL_NAME,
        "default_camera_source": DEFAULT_CAMERA_SOURCE,
        "latest": camera_worker.latest_risk(),
    }


@app.get("/camera/default-source")
def default_camera_source():
    return {"source": DEFAULT_CAMERA_SOURCE}


@app.get("/cameras/probe")
def probe_cameras(max_index: int = 8):
    return {"items": camera_worker.probe_sources(max_index=max(0, min(max_index, 20)))}


@app.post("/start")
def start(
    body: StartBody = StartBody(),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return camera_worker.start(_normalize_camera_source(body.source))


@app.post("/stop")
def stop(current_user: Dict[str, Any] = Depends(get_current_user)):
    return camera_worker.stop()


@app.get("/latest")
def latest():
    return camera_worker.latest_risk()


@app.get("/risk/latest")
def risk_latest():
    return camera_worker.latest_risk()


@app.get("/stream/raw.mjpg")
def stream_raw():
    return StreamingResponse(_mjpeg_generator(processed=False), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/stream/processed.mjpg")
def stream_processed():
    return StreamingResponse(_mjpeg_generator(processed=True), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/scene/config")
def get_scene_config():
    return scene_store.load()


@app.post("/scene/config")
def update_scene_config(
    body: SceneConfigBody,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    patch: Dict[str, Any] = {}
    if body.calibration_points is not None:
        if len(body.calibration_points) > 4:
            raise HTTPException(status_code=400, detail="Calibration supports up to 4 points.")
        patch["calibration_points"] = [_point_dict(p) for p in body.calibration_points]
    if body.entry_points is not None:
        patch["entry_points"] = [_point_dict(p) for p in body.entry_points]
    if body.exit_points is not None:
        patch["exit_points"] = [_point_dict(p) for p in body.exit_points]
    if body.risk_thresholds is not None:
        patch["risk_thresholds"] = body.risk_thresholds
    return scene_store.update(patch)


@app.post("/scene/calibration")
def set_calibration(
    points: List[Point],
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if len(points) != 4:
        raise HTTPException(status_code=400, detail="Calibration requires exactly 4 points.")
    return scene_store.update({"calibration_points": [_point_dict(p) for p in points]})


@app.post("/scene/entry-points")
def set_entry_points(
    points: List[Point],
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return scene_store.update({"entry_points": [_point_dict(p) for p in points]})


@app.post("/scene/exit-points")
def set_exit_points(
    points: List[Point],
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return scene_store.update({"exit_points": [_point_dict(p) for p in points]})


@app.get("/alerts")
def get_alerts(current_user: Dict[str, Any] = Depends(get_current_user)):
    return {"items": alert_manager.list_alerts()}


@app.post("/alerts/{alert_id}/ack")
def acknowledge_alert(
    alert_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    alert = alert_manager.acknowledge(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return alert


@app.websocket("/ws/risk")
async def risk_socket(websocket: WebSocket, token: Optional[str] = Query(None)):
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return
    try:
        jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        await websocket.close(code=4008, reason="Invalid token")
        return

    await websocket.accept()
    try:
        while True:
            await websocket.send_json(camera_worker.latest_risk())
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return
