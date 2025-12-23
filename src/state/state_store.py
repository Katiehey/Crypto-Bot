import json
import os
from datetime import datetime


class StateStore:
    def __init__(self, path="state/paper_state.json"):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

        if not os.path.exists(self.path):
            self._write({
                "equity": 500,
                "positions": {},
                "trade_log": [],
                "last_update": None,
            })

    def load(self):
        with open(self.path, "r") as f:
            return json.load(f)

    def save(self, state):
        state["last_update"] = datetime.utcnow().isoformat()
        with open(self.path, "w") as f:
            json.dump(state, f, indent=2)
