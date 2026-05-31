import json
import os
import threading
from typing import Any, Dict, List


Point = Dict[str, Any]


DEFAULT_CONFIG = {
    "calibration_points": [],
    "entry_points": [],
    "exit_points": [],
    "risk_thresholds": {
        "warning": 20,
        "high": 30,
        "critical": 40,
    },
}


class SceneConfigStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            self.save(DEFAULT_CONFIG)

    def load(self) -> Dict[str, Any]:
        with self._lock:
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                data = dict(DEFAULT_CONFIG)

            merged = dict(DEFAULT_CONFIG)
            merged.update(data)
            merged["risk_thresholds"] = {
                **DEFAULT_CONFIG["risk_thresholds"],
                **data.get("risk_thresholds", {}),
            }
            return merged

    def save(self, config: Dict[str, Any]) -> Dict[str, Any]:
        clean = dict(DEFAULT_CONFIG)
        clean.update(config)
        clean["calibration_points"] = self._clean_points(clean.get("calibration_points", []))
        clean["entry_points"] = self._clean_points(clean.get("entry_points", []))
        clean["exit_points"] = self._clean_points(clean.get("exit_points", []))

        with self._lock:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(clean, f, indent=2)
        return clean

    def update(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        config = self.load()
        config.update(patch)
        return self.save(config)

    @staticmethod
    def _clean_points(points: List[Point]) -> List[Point]:
        clean = []
        for i, point in enumerate(points):
            if "x" not in point or "y" not in point:
                continue
            clean.append(
                {
                    "id": str(point.get("id") or f"point_{i + 1}"),
                    "label": str(point.get("label") or point.get("id") or f"Point {i + 1}"),
                    "x": float(point["x"]),
                    "y": float(point["y"]),
                }
            )
        return clean
