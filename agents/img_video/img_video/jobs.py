"""Job store. One folder per job under jobs/. A stage re-runs only when the fingerprint of its inputs changes or its outputs are missing (never just because a file exists:
skip-if-exists once let a stale clip fake a 121 s speed-up). Everything a stage writes goes in the job folder; state.json says what happened and how long it took."""
import fcntl
import hashlib
import json
import re
import sys
import threading
import time
from pathlib import Path

from . import progress


def fingerprint(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


class Job:
    def __init__(self, root: Path, jid: str):
        self.id, self.dir = jid, Path(root) / jid
        self.state = json.loads((self.dir / "state.json").read_text())

    @classmethod
    def create(cls, root, request: dict):
        slug = re.sub(r"[^a-z0-9]+", "-", request["query"].lower())[:32].strip("-") or "job"
        jid = time.strftime("%Y%m%d-%H%M%S") + "-" + slug
        d = Path(root) / jid; d.mkdir(parents=True)
        (d / "state.json").write_text(json.dumps({"id": jid, "request": request, "status": "queued", "created": time.time(), "stages": {}}, indent=1))
        return cls(root, jid)

    @classmethod
    def load(cls, root, jid): return cls(root, jid)

    PHOTO_TYPES = (".jpg", ".jpeg", ".png", ".webp")
    MAX_PHOTOS, MAX_PHOTO_BYTES = 6, 20_000_000

    def add_references(self, photos):
        """Copies the photos of the people in the story into the job folder (a resume keeps them) and records them in the request as names relative to the job, with the label the user gave each photo ("me", "my wife"; "" when none).
        A photo is a path or a (path, label) pair. Raises ValueError for a missing or unsuitable file."""
        pairs = [(p, "") if isinstance(p, (str, Path)) else (p[0], str(p[1] or "").strip()[:60]) for p in photos][:self.MAX_PHOTOS]; paths = [Path(p).expanduser() for p, _ in pairs]
        d = self.dir / "reference"; d.mkdir(exist_ok=True, mode=0o700); names = []
        for k, p in enumerate(paths, 1):
            if p.suffix.lower() not in self.PHOTO_TYPES or not p.is_file(): raise ValueError(f"reference photo {p.name!r} must be a jpg, png or webp file")
            if p.stat().st_size > self.MAX_PHOTO_BYTES: raise ValueError(f"reference photo {p.name!r} is larger than {self.MAX_PHOTO_BYTES // 1_000_000} MB")
            dest = d / f"ref{k}{p.suffix.lower()}"; dest.write_bytes(p.read_bytes()); dest.chmod(0o600); names.append(f"reference/{dest.name}")
        self.state["request"]["references"] = names
        if any(w for _, w in pairs): self.state["request"]["reference_who"] = [w for _, w in pairs]
        self.save(); return names

    def reference_paths(self): return [self.dir / n for n in self.state["request"].get("references", [])]

    def reference_hashes(self): return [hashlib.sha256(p.read_bytes()).hexdigest()[:16] for p in self.reference_paths() if p.exists()]

    _save_lock = threading.Lock()

    def save(self):
        with self._save_lock: (self.dir / "state.json").write_text(json.dumps(self.state, indent=1, ensure_ascii=False))

    def log(self, msg):
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        print(line, file=sys.stderr, flush=True)        # stderr: stdout is reserved for results (--json)
        with open(self.dir / "log.txt", "a") as f: f.write(line + "\n")

    def lock(self):
        f = open(self.dir / ".lock", "w")
        try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError(f"job {self.id} is already running")
        return f

    def write(self, name, obj): (self.dir / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False))

    def read(self, name): return json.loads((self.dir / name).read_text())

    def run_stage(self, name, inputs, fn, outputs=()):
        """Run fn() unless this stage already finished with the same input fingerprint and all its output files exist. Returns True if it ran."""
        fp = fingerprint(inputs); st = self.state["stages"].get(name, {})
        if st.get("status") == "done" and st.get("fp") == fp and all((self.dir / o).exists() for o in outputs):
            self.log(f"stage {name}: unchanged inputs, reusing results"); progress.stage(name, "done"); return False
        self.log(f"stage {name}: running"); t = time.time(); progress.stage(name, "running")
        self.state["stages"][name] = {"status": "running", "fp": fp}; self.save()
        try:
            fn()
        except Exception as e:                                                       # noqa: BLE001
            self.state["stages"][name] = {"status": "failed", "fp": fp, "error": str(e)[:500], "secs": round(time.time() - t, 1)}; self.state["status"] = "failed"; self.save(); raise
        self.state["stages"][name] = {"status": "done", "fp": fp, "secs": round(time.time() - t, 1)}; self.save(); progress.stage(name, "done")
        self.log(f"stage {name}: done in {time.time() - t:.1f}s"); return True
