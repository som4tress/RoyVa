"""Detached runner for ONE director job (a picture set or a video), started by server.py so the chat can be answered at once. It runs the img_video agent, copies the results into RoyVa's picture / video folders
(the only places the bridge uploads from) and leaves one file in the outbox: <outbox>/done/<job>.json, written atomically, success or failure. The bridge posts it to the chat that asked.
usage: python3 runner.py '<json spec: {"job", "kind": "set"|"video", "query", "count", "aspect"}>'   Overrides: ROYVA_IMAGE_DIR, ROYVA_VIDEO_DIR, ROYVA_OUTBOX_DIR, ROYVA_IMGVIDEO_CMD (JSON list, for tests)."""
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = Path(os.environ.get("ROYVA_IMGVIDEO_DIR", ROOT / "agents" / "img_video"))
IMAGE_DIR = Path(os.environ.get("ROYVA_IMAGE_DIR", ROOT / "runtime" / "data" / "images"))
VIDEO_DIR = Path(os.environ.get("ROYVA_VIDEO_DIR", ROOT / "runtime" / "data" / "videos"))
OUTBOX = Path(os.environ.get("ROYVA_OUTBOX_DIR", ROOT / "runtime" / "data" / "outbox"))
TIMEOUT = {"set": int(os.environ.get("ROYVA_IMGSET_TIMEOUT", "2400")), "video": int(os.environ.get("ROYVA_IMGVIDEO_TIMEOUT", "3600"))}
KEEP_IMAGES, KEEP_VIDEOS = 80, 12
GRACE_S = 20                      # after a cancel the agent gets this long to tell ComfyUI to interrupt and exit before it is killed


def agent_cmd(spec):
    extra = []
    if spec.get("research_text"):                      # facts the caller already found: the agent skips its own web research
        f = OUTBOX / "logs" / f"{spec['job']}.research.txt"; f.parent.mkdir(parents=True, exist_ok=True); f.write_text(spec["research_text"]); extra = ["--research-file", str(f)]
    if os.environ.get("ROYVA_IMGVIDEO_CMD"):
        return json.loads(os.environ["ROYVA_IMGVIDEO_CMD"]) + [spec["query"]] + (["--video"] if spec["kind"] == "video" else []) + extra
    return (["/usr/bin/python3", "-m", "img_video", "run", spec["query"], "--aspect", spec.get("aspect", "1:1"), "--json"] + (["--count", str(spec["count"])] if spec.get("count") else [])
            + (["--video"] if spec["kind"] == "video" else []) + extra)


def finish(job, payload):
    d = OUTBOX / "done"; d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".{job}.tmp"; tmp.write_text(json.dumps({"job": job, **payload}, ensure_ascii=False)); os.replace(tmp, d / f"{job}.json")


def prune(folder, pattern, keep):
    for f in sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)[keep:]:
        try: f.unlink()
        except OSError: pass


def run_agent(spec):
    """Run the agent as its own process group, with its progress file in the outbox; poll once a second for a cancel marker (outbox/cancel/<job>, written by the bridge's Stop button) and for the time limit.
    Returns (stdout, stderr, how) with how in ok / cancelled / timeout. stdout and stderr go to files: a long, chatty job must never fill a pipe and hang."""
    job = spec["job"]; (OUTBOX / "progress").mkdir(parents=True, exist_ok=True); (OUTBOX / "logs").mkdir(parents=True, exist_ok=True); cancel = OUTBOX / "cancel" / job
    out, err = OUTBOX / "logs" / f"{job}.agent.out", OUTBOX / "logs" / f"{job}.agent.err"
    env = dict(os.environ, IMG_VIDEO_PROGRESS_FILE=str(OUTBOX / "progress" / f"{job}.json"))
    with open(out, "w") as fo, open(err, "w") as fe:
        proc = subprocess.Popen(agent_cmd(spec), cwd=AGENT_DIR, stdout=fo, stderr=fe, stdin=subprocess.DEVNULL, env=env, start_new_session=True)
        t0 = time.time(); how = "ok"
        while proc.poll() is None:
            if cancel.exists(): how = "cancelled"
            elif time.time() - t0 > (spec.get("timeout") or TIMEOUT[spec["kind"]]): how = "timeout"
            if how != "ok":
                try: os.killpg(proc.pid, signal.SIGTERM)                  # the agent tells ComfyUI to interrupt its current job, then exits
                except ProcessLookupError: break
                try: proc.wait(GRACE_S)
                except subprocess.TimeoutExpired:
                    try: os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    proc.wait()
                break
            time.sleep(1)
    return out.read_text(), err.read_text(), how


def produce(spec):
    """Run the agent for one spec and return the result payload (what finish() writes): {"ok", "kind", ...}. Used by main() (background job: the payload goes to the outbox) and by server.py (synchronous mode:
    the payload becomes the tool result)."""
    kind = spec["kind"]
    stdout, stderr, how = run_agent(spec)
    if how == "cancelled": return {"ok": False, "kind": kind, "cancelled": True, "error": "stopped"}
    if how == "timeout": return {"ok": False, "kind": kind, "error": f"it did not finish within {(spec.get('timeout') or TIMEOUT[kind]) // 60} minutes"}
    lines = [l for l in stdout.splitlines() if l.strip().startswith("{")]
    if not lines: return {"ok": False, "kind": kind, "error": "the agent returned nothing usable: " + (stderr.strip().splitlines() or ["no output"])[-1][:200]}
    res = json.loads(lines[-1])
    if not res.get("ok"): return {"ok": False, "kind": kind, "error": str(res.get("error") or "the agent failed")[:300]}
    secs = res.get("stage_seconds") or {}
    if kind == "video":
        v = res.get("video") or {}; src = Path(v.get("path", ""))
        if not src.is_file(): return {"ok": False, "kind": kind, "error": "the finished video is missing on disk"}
        VIDEO_DIR.mkdir(parents=True, exist_ok=True); dst = VIDEO_DIR / f"video-{res['job']}.mp4"; shutil.copy2(src, dst); prune(VIDEO_DIR, "video-*.mp4", KEEP_VIDEOS)
        return {"ok": True, "kind": "video", "title": v.get("title") or res.get("title", ""), "video": {"path": str(dst), "seconds": v.get("seconds"), "mb": v.get("mb")}, "stage_seconds": secs}
    IMAGE_DIR.mkdir(parents=True, exist_ok=True); imgs = []
    for im in res.get("images", []):
        src = Path(im["path"])
        if not src.is_file(): return {"ok": False, "kind": kind, "error": f"picture {im.get('index')} is missing on disk"}
        dst = IMAGE_DIR / f"imgset-{res['job']}-{int(im['index']):02d}.png"; shutil.copy2(src, dst)
        imgs.append({"path": str(dst), "index": im["index"], "topic": im["topic"], "caption": im["caption"]})
    prune(IMAGE_DIR, "imgset-*.png", KEEP_IMAGES)
    return {"ok": True, "kind": "images", "title": res.get("title", ""), "images": imgs, "stage_seconds": secs}


def main(spec):
    finish(spec["job"], produce(spec))


if __name__ == "__main__":
    spec = json.loads(sys.argv[1])
    try:
        main(spec)
    except Exception as e:                                           # noqa: BLE001  (the chat must always hear back)
        finish(spec["job"], {"ok": False, "kind": spec.get("kind", "set"), "error": f"{type(e).__name__}: {str(e)[:250]}"})
