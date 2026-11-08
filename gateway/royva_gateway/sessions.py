"""Gateway-side session memory: which intents/tools a conversation has used. One JSON file, written atomically."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .models import SessionState


class SessionStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._data: dict[str, SessionState] = {}
        if self.path.exists():
            for sid, raw in json.loads(self.path.read_text()).items():
                self._data[sid] = SessionState.model_validate(raw)

    def get(self, sid: Optional[str]) -> Optional[SessionState]:
        return self._data.get(sid) if sid else None

    def count(self) -> int:
        return len(self._data)

    def prune(self, max_age_days: int = 30, max_sessions: int = 5000, now: Optional[datetime] = None) -> int:
        """Drop sessions idle longer than max_age_days, then the oldest beyond max_sessions. Returns how many were removed."""
        now = now or datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=max_age_days)).isoformat()
        stamp = lambda st: st.updated_at or st.created_at
        keep = {k: v for k, v in self._data.items() if stamp(v) >= cutoff}
        if len(keep) > max_sessions:
            keep = dict(sorted(keep.items(), key=lambda kv: stamp(kv[1]))[-max_sessions:])
        removed = len(self._data) - len(keep)
        if removed:
            with self._lock:
                self._data = keep
                self._write()
        return removed

    def _write(self) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.path.parent)
        with os.fdopen(fd, "w") as f:
            json.dump({k: v.model_dump() for k, v in self._data.items()}, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    def put(self, state: SessionState) -> None:
        with self._lock:
            self._data[state.session_id] = state
            self._write()
