import json
import os
from datetime import datetime


class Heartbeat:
    def __init__(self, path="state/heartbeat.json"):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def beat(self, status: str, details: dict = None):
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "status": status,
            "details": details or {},
        }

        with open(self.path, "w") as f:
            json.dump(payload, f, indent=2)
