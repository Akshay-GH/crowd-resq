import os
import platform
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
from ultralytics import YOLO

from .alert_manager import AlertManager
from .risk_engine import RiskEngine
from .scene_config import SceneConfigStore


class CameraWorker:
    def __init__(
        self,
        scene_store: SceneConfigStore,
        alert_manager: AlertManager,
        model_path: str,
    ):
        self.scene_store = scene_store
        self.alert_manager = alert_manager
        self.model_path = model_path
        self.risk_engine = RiskEngine()
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._model: Optional[YOLO] = None
        self._latest_raw: Optional[bytes] = None
        self._latest_processed: Optional[bytes] = None
        self._latest_risk: Dict[str, Any] = {
            "ready": False,
            "people_count": 0,
            "risk_score": 0,
            "risk_level": "NORMAL",
            "message": "Camera is not running.",
        }
        self._last_positions: Dict[int, Tuple[float, float, float]] = {}
        self._det_conf = _env_float("CROWD_CONF", 0.25)
        self._det_iou = _env_float("CROWD_IOU", 0.6)
        self._det_imgsz = _env_int("CROWD_IMGSZ", 1280)

    @property
    def running(self) -> bool:
        return self._running

    def start(self, source: Union[int, str] = 0) -> Dict[str, Any]:
        if self._running:
            return {"ok": True, "status": "already_running"}
        self._running = True
        with self._lock:
            self._latest_raw = None
            self._latest_processed = None
            self._latest_risk = {
                "ready": False,
                "people_count": 0,
                "risk_score": 0,
                "risk_level": "NORMAL",
                "message": f"Starting camera source: {source}",
            }
        self._thread = threading.Thread(target=self._loop, args=(source,), daemon=True)
        self._thread.start()
        return {"ok": True, "status": "started", "source": source}

    def stop(self) -> Dict[str, Any]:
        self._running = False
        return {"ok": True, "status": "stopping"}

    def latest_risk(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._latest_risk)

    def latest_jpeg(self, processed: bool = True) -> Optional[bytes]:
        with self._lock:
            return self._latest_processed if processed else self._latest_raw

    def probe_sources(self, max_index: int = 8) -> List[Dict[str, Any]]:
        results = []
        for index in range(max_index + 1):
            cap, backend_name = self._open_capture(index)
            ok = False
            width = height = 0
            if cap is not None and cap.isOpened():
                ok, frame = cap.read()
                if ok and frame is not None:
                    height, width = frame.shape[:2]
                cap.release()
            results.append(
                {
                    "source": index,
                    "available": bool(ok),
                    "backend": backend_name,
                    "width": int(width),
                    "height": int(height),
                }
            )
        return results

    def _load_model(self) -> YOLO:
        if self._model is None:
            is_local_path = os.path.sep in self.model_path or self.model_path.startswith(".")
            if is_local_path and not os.path.exists(self.model_path):
                raise FileNotFoundError(f"YOLO weights not found: {self.model_path}")
            self._model = YOLO(self.model_path)
        return self._model

    def _loop(self, source: Union[int, str]) -> None:
        cap, backend_name = self._open_capture(source)
        if cap is None or not cap.isOpened():
            self._set_error(f"Could not open camera source: {source}")
            self._running = False
            return

        try:
            model = self._load_model()
        except Exception as exc:
            self._set_error(str(exc))
            cap.release()
            self._running = False
            return

        heatmap_acc: Optional[np.ndarray] = None
        while self._running:
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.05)
                continue

            height, width = frame.shape[:2]
            if heatmap_acc is None:
                heatmap_acc = np.zeros((height, width), dtype=np.float32)

            scene = self._scene_with_ground_points(width, height)
            people, boxes = self._detect_people(model, frame, width, height, scene.get("homography"))
            risk = self.risk_engine.evaluate(people, scene)
            alert = self.alert_manager.create_alert(risk)
            if alert:
                risk["alert"] = alert

            processed = self._draw_overlay(frame, boxes, people, risk, scene, heatmap_acc)
            raw_jpeg = self._encode(frame)
            processed_jpeg = self._encode(processed)

            with self._lock:
                self._latest_raw = raw_jpeg
                self._latest_processed = processed_jpeg
                self._latest_risk = risk

            time.sleep(0.01)

        cap.release()

    def _open_capture(self, source: Union[int, str]) -> Tuple[Optional[cv2.VideoCapture], str]:
        if isinstance(source, str) and not source.strip().isdigit():
            cap = cv2.VideoCapture(source)
            return cap, "url/default"

        index = int(source)
        backend_options: List[Tuple[str, int]] = []
        if platform.system().lower() == "windows":
            backend_options.extend(
                [
                    ("dshow", cv2.CAP_DSHOW),
                    ("msmf", cv2.CAP_MSMF),
                ]
            )
        backend_options.append(("default", cv2.CAP_ANY))

        for name, backend in backend_options:
            cap = cv2.VideoCapture(index, backend)
            if not cap.isOpened():
                cap.release()
                continue
            ok, frame = cap.read()
            if ok and frame is not None:
                return cap, name
            cap.release()
        return None, "unavailable"

    def _detect_people(
        self,
        model: YOLO,
        frame: np.ndarray,
        width: int,
        height: int,
        homography: Optional[np.ndarray],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        try:
            result = model.track(
                frame,
                conf=self._det_conf,
                iou=self._det_iou,
                imgsz=self._det_imgsz,
                classes=[0],
                persist=True,
                tracker="bytetrack.yaml",
                verbose=False,
            )[0]
        except Exception:
            result = model.predict(
                frame,
                conf=self._det_conf,
                iou=self._det_iou,
                imgsz=self._det_imgsz,
                classes=[0],
                verbose=False,
            )[0]

        if result.boxes is None or len(result.boxes) == 0:
            return [], []

        xyxy = result.boxes.xyxy.cpu().numpy()
        confs = result.boxes.conf.cpu().numpy()
        ids = result.boxes.id.cpu().numpy().astype(int) if result.boxes.id is not None else np.arange(len(xyxy))

        now = time.time()
        people: List[Dict[str, Any]] = []
        boxes: List[Dict[str, Any]] = []
        for i, box in enumerate(xyxy):
            x1, y1, x2, y2 = [float(v) for v in box]
            foot_x = (x1 + x2) / 2.0
            foot_y = y2
            track_id = int(ids[i])
            gx, gy = self._project_point(foot_x, foot_y, width, height, homography)

            prev = self._last_positions.get(track_id)
            vx = vy = speed = 0.0
            if prev:
                dt = max(0.001, now - prev[2])
                vx = (gx - prev[0]) / dt
                vy = (gy - prev[1]) / dt
                speed = float((vx * vx + vy * vy) ** 0.5)
            self._last_positions[track_id] = (gx, gy, now)

            people.append({"id": track_id, "gx": gx, "gy": gy, "vx": vx, "vy": vy, "speed": speed})
            boxes.append({"id": track_id, "xyxy": [x1, y1, x2, y2], "conf": float(confs[i])})

        keep_ids = {p["id"] for p in people}
        self._last_positions = {k: v for k, v in self._last_positions.items() if k in keep_ids}
        return people, boxes

    def _scene_with_ground_points(self, width: int, height: int) -> Dict[str, Any]:
        scene = self.scene_store.load()
        homography = self._homography(scene.get("calibration_points", []))
        scene["homography"] = homography

        for key in ("entry_points", "exit_points"):
            for point in scene.get(key, []):
                gx, gy = self._project_point(point["x"], point["y"], width, height, homography)
                point["gx"] = gx
                point["gy"] = gy
        return scene

    def _homography(self, points: List[Dict[str, Any]]) -> Optional[np.ndarray]:
        if len(points) != 4:
            return None
        src = np.array([[p["x"], p["y"]] for p in points], dtype=np.float32)
        s = src.sum(axis=1)
        diff = np.diff(src, axis=1)
        ordered = np.array([src[np.argmin(s)], src[np.argmin(diff)], src[np.argmax(s)], src[np.argmax(diff)]], dtype=np.float32)
        dst = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
        return cv2.getPerspectiveTransform(ordered, dst)

    def _project_point(self, x: float, y: float, width: int, height: int, homography: Optional[np.ndarray]) -> Tuple[float, float]:
        if homography is None:
            return min(1.0, max(0.0, x / max(1, width))), min(1.0, max(0.0, y / max(1, height)))
        p = cv2.perspectiveTransform(np.array([[[x, y]]], dtype=np.float32), homography)[0][0]
        return min(1.0, max(0.0, float(p[0]))), min(1.0, max(0.0, float(p[1])))

    def _draw_overlay(
        self,
        frame: np.ndarray,
        boxes: List[Dict[str, Any]],
        people: List[Dict[str, Any]],
        risk: Dict[str, Any],
        scene: Dict[str, Any],
        heatmap_acc: np.ndarray,
    ) -> np.ndarray:
        output = frame.copy()
        heatmap_acc *= 0.92
        height, width = output.shape[:2]

        for box in boxes:
            x1, y1, x2, y2 = [int(v) for v in box["xyxy"]]
            cx, cy = int((x1 + x2) / 2), int(y2)
            cv2.rectangle(output, (x1, y1), (x2, y2), (46, 204, 113), 2)
            cv2.putText(output, f"ID {box['id']}", (x1, max(16, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (46, 204, 113), 1)
            cv2.circle(heatmap_acc, (cx, cy), 26, 1.0, -1)

        blurred = cv2.GaussianBlur(heatmap_acc, (0, 0), 18)
        norm = cv2.normalize(blurred, None, 0, 255, cv2.NORM_MINMAX)
        heatmap = cv2.applyColorMap(norm.astype(np.uint8), cv2.COLORMAP_JET)
        output = cv2.addWeighted(output, 0.68, heatmap, 0.32, 0)

        for point in scene.get("entry_points", []):
            self._draw_point(output, point, (255, 191, 0), "ENTRY")
        for point in scene.get("exit_points", []):
            self._draw_point(output, point, (0, 255, 255), "EXIT")

        color = (46, 204, 113)
        if risk["risk_level"] == "WARNING":
            color = (0, 215, 255)
        elif risk["risk_level"] == "HIGH":
            color = (0, 140, 255)
        elif risk["risk_level"] == "CRITICAL":
            color = (0, 0, 255)

        cv2.rectangle(output, (10, 10), (430, 92), (20, 20, 20), -1)
        cv2.putText(output, f"Risk: {risk['risk_level']} ({risk['risk_score']})", (24, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.85, color, 2)
        cv2.putText(output, f"People: {risk['people_count']}  Avg speed: {risk['movement']['average_speed']}", (24, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 1)
        return output

    def _draw_point(self, frame: np.ndarray, point: Dict[str, Any], color: Tuple[int, int, int], label: str) -> None:
        x, y = int(point["x"]), int(point["y"])
        cv2.circle(frame, (x, y), 9, color, -1)
        cv2.putText(frame, f"{label}: {point.get('label', '')}", (x + 10, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    def _encode(self, frame: np.ndarray) -> Optional[bytes]:
        ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        return jpg.tobytes() if ok else None

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._latest_risk = {
                "ready": False,
                "people_count": 0,
                "risk_score": 0,
                "risk_level": "ERROR",
                "message": message,
            }


def _env_float(name: str, fallback: float) -> float:
    try:
        return float(os.getenv(name, "") or fallback)
    except ValueError:
        return fallback


def _env_int(name: str, fallback: int) -> int:
    try:
        return int(float(os.getenv(name, "") or fallback))
    except ValueError:
        return fallback
