import math
import time
from collections import deque
from typing import Any, Dict, List, Tuple

import numpy as np


class RiskEngine:
    def __init__(self, grid_size: int = 20):
        self.grid_size = grid_size
        self.history = deque(maxlen=120)

    def evaluate(
        self,
        people: List[Dict[str, Any]],
        scene_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        now = time.time()
        count = len(people)
        self.history.append((now, count))

        grid = np.zeros((self.grid_size, self.grid_size), dtype=np.int32)
        speeds = []
        for person in people:
            gx = min(self.grid_size - 1, max(0, int(person["gx"] * self.grid_size)))
            gy = min(self.grid_size - 1, max(0, int(person["gy"] * self.grid_size)))
            grid[gy, gx] += 1
            speeds.append(float(person.get("speed", 0.0)))

        max_cell = int(grid.max()) if count else 0
        avg_cell = float(grid.sum() / max(1, np.count_nonzero(grid))) if count else 0.0
        avg_speed = float(sum(speeds) / max(1, len(speeds)))
        low_speed_people = sum(1 for speed in speeds if speed < 0.015)

        density_score = min(100.0, max_cell * 14.0)
        congestion_score = min(100.0, (low_speed_people / max(1, count)) * density_score * 1.25)
        exit_score, exit_status = self._exit_score(people, scene_config.get("exit_points", []))
        growth_score = self._growth_score(now, count)
        flow_score = self._flow_score(people)

        risk_score = round(
            density_score * 0.35
            + congestion_score * 0.25
            + flow_score * 0.20
            + exit_score * 0.15
            + growth_score * 0.05,
            1,
        )

        thresholds = scene_config.get("risk_thresholds", {})
        level = "NORMAL"
        if risk_score >= thresholds.get("critical", 80):
            level = "CRITICAL"
        elif risk_score >= thresholds.get("high", 65):
            level = "HIGH"
        elif risk_score >= thresholds.get("warning", 40):
            level = "WARNING"

        hotspots = self._hotspots(grid)
        message = self._message(level, hotspots, exit_status)
        return {
            "ready": True,
            "ts": int(now),
            "people_count": count,
            "risk_score": risk_score,
            "risk_level": level,
            "message": message,
            "density": {
                "grid_size": self.grid_size,
                "max_cell_density": max_cell,
                "average_occupied_cell_density": round(avg_cell, 2),
                "hotspots": hotspots,
                "grid": grid.tolist(),
            },
            "movement": {
                "average_speed": round(avg_speed, 4),
                "low_speed_people": low_speed_people,
                "flow_score": round(flow_score, 1),
                "congestion_score": round(congestion_score, 1),
                "growth_score": round(growth_score, 1),
            },
            "exits": exit_status,
        }

    def _exit_score(self, people: List[Dict[str, Any]], exits: List[Dict[str, Any]]) -> Tuple[float, List[Dict[str, Any]]]:
        statuses = []
        worst = 0.0
        for exit_point in exits:
            ex = float(exit_point.get("gx", exit_point.get("x", 0.0)))
            ey = float(exit_point.get("gy", exit_point.get("y", 0.0)))
            nearby = 0
            for person in people:
                dist = math.hypot(person["gx"] - ex, person["gy"] - ey)
                if dist <= 0.16:
                    nearby += 1
            score = min(100.0, nearby * 8.0)
            worst = max(worst, score)
            statuses.append(
                {
                    "id": exit_point.get("id", "exit"),
                    "label": exit_point.get("label", "Exit"),
                    "nearby_people": nearby,
                    "status": "congested" if score >= 65 else "busy" if score >= 40 else "clear",
                }
            )
        return worst, statuses

    def _growth_score(self, now: float, count: int) -> float:
        previous = [item for item in self.history if now - item[0] >= 8]
        if not previous:
            return 0.0
        old_count = previous[0][1]
        growth = count - old_count
        return min(100.0, max(0.0, growth * 6.0))

    def _flow_score(self, people: List[Dict[str, Any]]) -> float:
        moving = [p for p in people if p.get("speed", 0.0) >= 0.015]
        if len(moving) < 4:
            return 0.0
        angles = [math.atan2(p.get("vy", 0.0), p.get("vx", 0.0)) for p in moving]
        x = sum(math.cos(a) for a in angles) / len(angles)
        y = sum(math.sin(a) for a in angles) / len(angles)
        alignment = math.hypot(x, y)
        return min(100.0, alignment * len(moving) * 4.0)

    def _hotspots(self, grid: np.ndarray) -> List[Dict[str, Any]]:
        hotspots = []
        threshold = max(4, int(grid.max() * 0.75)) if grid.max() else 999
        for y, x in np.argwhere(grid >= threshold):
            hotspots.append({"x": int(x), "y": int(y), "count": int(grid[y, x])})
        return sorted(hotspots, key=lambda h: h["count"], reverse=True)[:5]

    def _message(self, level: str, hotspots: List[Dict[str, Any]], exits: List[Dict[str, Any]]) -> str:
        congested_exit = next((e for e in exits if e["status"] == "congested"), None)
        if level in {"HIGH", "CRITICAL"} and congested_exit:
            return f"{level} stampede risk near {congested_exit['label']}. Redirect crowd and open alternate exits."
        if level in {"HIGH", "CRITICAL"} and hotspots:
            return "High crowd concentration detected. Deploy staff to disperse the hotspot."
        if level == "WARNING":
            return "Crowd risk is rising. Monitor density and prepare diversion."
        return "Crowd movement is within normal range."
