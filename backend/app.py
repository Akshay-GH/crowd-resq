import asyncio
import os
import time
from typing import Any, Dict, List, Optional, Union

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.alert_manager import AlertManager
from core.camera_worker import CameraWorker
from core.scene_config import SceneConfigStore


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_NAME = os.getenv("CROWD_MODEL", "yolo26n.pt")

scene_store = SceneConfigStore(os.path.join(DATA_DIR, "scene_config.json"))
alert_manager = AlertManager(os.path.join(DATA_DIR, "alerts.json"))
camera_worker = CameraWorker(scene_store, alert_manager, MODEL_NAME)

app = FastAPI(title="CrowdResQ Stampede Risk Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+):3000$",
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
    source: Optional[Union[int, str]] = 0


def _point_dict(point: Point) -> Dict[str, Any]:
    if hasattr(point, "model_dump"):
        return point.model_dump(exclude_none=True)
    return point.dict(exclude_none=True)


def _mjpeg_generator(processed: bool = True):
    boundary = "frame"
    while True:
        frame = camera_worker.latest_jpeg(processed=processed)
        if frame is None:
            time.sleep(0.05)
            continue
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
        "latest": camera_worker.latest_risk(),
    }


@app.get("/cameras/probe")
def probe_cameras(max_index: int = 8):
    return {"items": camera_worker.probe_sources(max_index=max(0, min(max_index, 20)))}


@app.post("/start")
def start(body: StartBody = StartBody()):
    return camera_worker.start(body.source if body.source is not None else 0)


@app.post("/stop")
def stop():
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
def update_scene_config(body: SceneConfigBody):
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
def set_calibration(points: List[Point]):
    if len(points) != 4:
        raise HTTPException(status_code=400, detail="Calibration requires exactly 4 points.")
    return scene_store.update({"calibration_points": [_point_dict(p) for p in points]})


@app.post("/scene/entry-points")
def set_entry_points(points: List[Point]):
    return scene_store.update({"entry_points": [_point_dict(p) for p in points]})


@app.post("/scene/exit-points")
def set_exit_points(points: List[Point]):
    return scene_store.update({"exit_points": [_point_dict(p) for p in points]})


@app.get("/alerts")
def get_alerts():
    return {"items": alert_manager.list_alerts()}


@app.post("/alerts/{alert_id}/ack")
def acknowledge_alert(alert_id: str):
    alert = alert_manager.acknowledge(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return alert


@app.websocket("/ws/risk")
async def risk_socket(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(camera_worker.latest_risk())
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return
