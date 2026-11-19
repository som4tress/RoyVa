"""Command line: python -m img_video <command>. Commands are added as the agent grows; `t2i` is a one-picture debug tool."""
import argparse
import sys
from pathlib import Path

from . import comfy, config, guard, pipeline, research, single
from .jobs import Job


def cmd_t2i(a, cfg, caps):
    base = cfg["comfy"]["url"]
    comfy.preflight(base, cfg["comfy"])
    w, h = (int(x) for x in a.size.split("x"))
    print(f"preflight ok; generating {w}x{h} with {cfg['comfy']['unet']}, {cfg['comfy']['steps']} steps", flush=True)
    comfy.wait_until_free(base, log=print)
    png, secs = comfy.generate_image(base, cfg["comfy"], a.prompt, w, h, a.seed)
    Path(a.out).write_bytes(png)
    print(f"wrote {a.out} ({len(png) / 1e6:.2f} MB) in {secs:.1f}s")


def cmd_research(a, cfg, caps):
    r = research.ask(cfg["research"], a.question)
    print(f"provider={r['provider']} intents={r['intents']} in {r['secs']:.1f}s\n")
    print(r["text"])


def cmd_image(a, cfg, caps):
    import json as _json
    text = sys.stdin.read() if a.stdin else (a.prompt or "")
    size = tuple(int(x) for x in a.size.split("x")) if a.size else None
    r = single.make_image(cfg, caps, text, aspect=a.aspect, size=size, seed=a.seed)
    print(_json.dumps(r, ensure_ascii=False) if a.json else (r.get("image_path") or r.get("error")))
    if not r["ok"]: raise SystemExit(2)


def cmd_fit(a, cfg, caps):
    import json as _json
    text = sys.stdin.read() if a.stdin else (a.prompt or "")
    r = guard.fit_prompt(cfg, text, cap=a.cap)
    print(_json.dumps(r, ensure_ascii=False) if a.json else r["prompt"])


def _stop_on_sigterm(cfg):
    """SIGTERM means the owner pressed Stop: tell ComfyUI to interrupt the graph it is running, then leave (the finally blocks release the GPU lock)."""
    import signal
    def handler(signum, frame):
        comfy.interrupt(cfg["comfy"]["url"]); raise SystemExit(143)
    signal.signal(signal.SIGTERM, handler)


def cmd_run(a, cfg, caps):
    import json as _json
    _stop_on_sigterm(cfg)
    root = config.jobs_dir(cfg); root.mkdir(parents=True, exist_ok=True)
    if a.job: job = Job.load(root, a.job)
    else:
        req = {"query": a.query, "count": a.count, "aspect": a.aspect, "video": bool(a.video)}
        if getattr(a, "research_file", None): req["research_text"] = Path(a.research_file).read_text()
        job = Job.create(root, req)
    if not a.json: print(f"job {job.id}")
    try:
        pipeline.run(job, cfg, caps, stop_after=a.stop_after, with_video=a.video)
    except Exception as e:                                     # noqa: BLE001  (with --json a failure is still a machine-readable answer)
        if not a.json: raise
        print(_json.dumps({"ok": False, "job": job.id, "error": str(e)[:400]})); raise SystemExit(2)
    if a.json:
        res = job.read("result.json") if job.state["status"] == "done" else {}
        if res and a.video: res["video"] = job.read("video.json")
        print(_json.dumps({"ok": job.state["status"] == "done", "job": job.id, **res}, ensure_ascii=False))
    elif job.state["status"] == "done": print(job.dir / "result.json")


def cmd_status(a, cfg, caps):
    job = Job.load(config.jobs_dir(cfg), a.job); print(job.id, job.state["status"])
    for k, v in job.state["stages"].items(): print(f"  {k:9s} {v['status']:8s} {v.get('secs', '')}s {v.get('error', '')}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="img_video", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("t2i", help="generate one picture (debug)")
    t.add_argument("prompt"); t.add_argument("--out", default="t2i.png"); t.add_argument("--size", default="720x1280"); t.add_argument("--seed", type=int, default=1)
    t.set_defaults(fn=cmd_t2i)
    r = sub.add_parser("research", help="ask one web-research question through the configured provider (debug)")
    r.add_argument("question"); r.set_defaults(fn=cmd_research)
    rn = sub.add_parser("run", help="run a job: query -> plan -> research -> items -> images -> result")
    rn.add_argument("query", nargs="?"); rn.add_argument("--count", type=int); rn.add_argument("--aspect", default="9:16", choices=["9:16", "16:9", "1:1"])
    rn.add_argument("--video", action="store_true", help="after the pictures, narrate and animate them into a video"); rn.add_argument("--json", action="store_true", help="print only one JSON object on stdout (logs go to stderr)"); rn.add_argument("--job", help="resume an existing job id"); rn.add_argument("--stop-after", choices=pipeline.STAGES); rn.set_defaults(fn=cmd_run)
    rn.add_argument("--research-file", help="use the text in this file as the web research instead of asking the gateway (no gateway call is made)")
    im = sub.add_parser("image", help="one picture from the user's own words (no director): shortened by the guard if long, drawn on the 3090 (this machine's GPU as the fallback)")
    im.add_argument("prompt", nargs="?"); im.add_argument("--stdin", action="store_true"); im.add_argument("--aspect", default="1:1", choices=["9:16", "16:9", "1:1"]); im.add_argument("--size", help="WxH, overrides --aspect")
    im.add_argument("--seed", type=int); im.add_argument("--json", action="store_true"); im.set_defaults(fn=cmd_image)
    ft = sub.add_parser("fit", help="shorten a picture prompt of any length to the cap (rewrite by the local writer, then a word-boundary cut); used by the chat image tool before it reaches the 3090")
    ft.add_argument("prompt", nargs="?"); ft.add_argument("--stdin", action="store_true"); ft.add_argument("--cap", type=int); ft.add_argument("--json", action="store_true"); ft.set_defaults(fn=cmd_fit)
    st = sub.add_parser("status", help="show a job's stages"); st.add_argument("job"); st.set_defaults(fn=cmd_status)
    a = ap.parse_args(argv)
    cfg, caps = config.load()
    try:
        a.fn(a, cfg, caps)
    except (comfy.ComfyError, research.ResearchError) as e:
        print(f"ERROR: {e}", file=sys.stderr); return 2
    return 0
