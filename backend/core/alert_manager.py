import json
import os
import threading
import time
from typing import Any, Dict, List, Optional


class AlertManager:
    def __init__(self, path: str, cooldown_seconds: int = 20):
        self.path = path
        self.cooldown_seconds = cooldown_seconds

        self._lock = threading.Lock()
        self._last_alert_at = 0.0
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            self._write([])

    def list_alerts(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self._read()

    def create_alert(self, risk: Dict[str, Any], reason: Optional[str] = None) -> Optional[Dict[str, Any]]:
        
        now = time.time()
        if risk.get("risk_level") not in {"HIGH", "CRITICAL"}:
            return None
          

        alert = {
            "id": f"alert_{int(now)}",
            "ts": int(now),
            "level": risk.get("risk_level"),
            "score": risk.get("risk_score"),
            "message": reason or risk.get("message") or "High stampede risk detected.",
            "details": {
                "people_count": risk.get("people_count", 0),
                "hotspots": risk.get("density", {}).get("hotspots", []),
                "exits": risk.get("exits", []),
            },
            "acknowledged": False,
        }

        with self._lock:
            if now - self._last_alert_at < self.cooldown_seconds:
                          return None
            alerts = self._read()
            alerts.insert(0, alert)
            self._write(alerts[:100])
            self._last_alert_at = now
        return alert

    def acknowledge(self, alert_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            alerts = self._read()
            for alert in alerts:
                if alert["id"] == alert_id:
                    alert["acknowledged"] = True
                    self._write(alerts)
                    return alert
        return None

    def _read(self) -> List[Dict[str, Any]]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _write(self, alerts):
      tmp = self.path + ".tmp"
      with open(tmp, "w", encoding="utf-8") as f:
          json.dump(alerts, f, indent=2)
      os.replace(tmp, self.path)
