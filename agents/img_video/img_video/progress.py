"""Live progress for whoever started the job (the Telegram bridge turns it into the live status message). When IMG_VIDEO_PROGRESS_FILE is set, every stage change and every finished shot / picture rewrites that
small JSON file atomically: {"kind", "started", "ts", "stages": {name: running|done}, "shots_done", "shots_total", "pictures_done", "pictures_total"}. With the variable unset (every other use) nothing is written."""
import json
import os
import threading
import time

_state = {}
_lock = threading.Lock()


def update(**kw):
    p = os.environ.get("IMG_VIDEO_PROGRESS_FILE")
    if not p: return
    with _lock:
        _state.update(kw); _state["ts"] = round(time.time(), 1)
        tmp = p + ".tmp"
        try:
            with open(tmp, "w") as f: json.dump(_state, f)
            os.replace(tmp, p)
        except OSError: pass                                      # progress is a courtesy: it must never stop a render


def stage(name, status):
    with _lock: _state.setdefault("stages", {})[name] = status
    update()


def reset():
    with _lock: _state.clear()
