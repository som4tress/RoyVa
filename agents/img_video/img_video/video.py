"""Animation stages for a finished image set: storyboard (local LLM) -> voice (CPU) || clips (3090) -> video (ffmpeg). Everything lands in <job>/video/.
Nothing here is specific to a topic: the pictures, captions and the model decide the content; capabilities.json and config.toml decide the numbers."""
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import config, guard, wan


def vdir(job):
    d = job.dir / "video"; d.mkdir(exist_ok=True); return d


def clip_seconds(caps):
    v = caps["video"]; return v["frames"] / v["wan_fps"]


def max_shots(cfg, caps, narrated):
    """The most shots a video may have so that it stays within [limits] max_video_seconds. A shot runs clip_seconds, or up to clip_seconds * max_slow when it is slowed to fit its voice, and shots overlap by the dissolve:
    n shots last n * per - (n - 1) * xf, so n <= (limit - xf) / (per - xf)."""
    xf = caps["padding"]["crossfade_seconds"]; per = clip_seconds(caps) * (caps["video"]["max_slow"] if narrated else 1.0)
    return max(1, int((cfg["limits"]["max_video_seconds"] - xf) / (per - xf)))


def narration_budget(caps):
    """Characters one narration line may have: the clip may be slowed by max_slow to fit a longer line, minus the lead-in and tail padding, times the measured speaking rate."""
    v, p = caps["video"], caps["padding"]
    return int((clip_seconds(caps) * v["max_slow"] - p["lead_seconds"] - p["tail_seconds"]) * config.cap(caps, "tts_chars_per_second"))


def storyboard(job, cfg, caps):
    """No model call: the director already wrote motion and narration for every shot (with the narration length budget). This only attaches the pictures and the sizes."""
    vdir(job); res, dr = job.read("result.json"), job.read("direction.json"); sz = caps["video"]["sizes"][job.state["request"]["aspect"]]
    narrated = job.read("plan.json").get("narrated", True)
    job.write("video/storyboard.json", {"title": res["title"], "narrated": narrated, "narration_char_budget": narration_budget(caps), "clip_seconds": round(clip_seconds(caps), 2), "wan": sz["wan"], "out": sz["out"],
        "shots": [{"i": i, "image": im["path"], "topic": im["topic"], "motion": s["motion"], "narration": s.get("narration", "")} for i, (im, s) in enumerate(zip(res["images"], dr["shots"]), 1)]})


def voice(job, cfg, caps):
    py = os.path.expanduser(cfg["tts"]["python"]); sb = vdir(job) / "storyboard.json"
    r = subprocess.run([py, str(Path(__file__).with_name("voice_worker.py")), str(sb), str(cfg["voice"]["exaggeration"]), str(cfg["voice"]["cfg_weight"])], capture_output=True, text=True)
    (vdir(job) / "voice.log").write_text(r.stdout + r.stderr)
    if r.returncode != 0: raise RuntimeError("voice failed: " + (r.stderr or r.stdout)[-300:])


def clips(job, cfg, caps):
    with guard.gpu_lock(log=job.log): _clips(job, cfg, caps)


def _clips(job, cfg, caps):
    sb = job.read("video/storyboard.json"); d = vdir(job)
    T = wan.animate(cfg, caps, [{"i": s["i"], "image": s["image"], "motion": s["motion"]} for s in sb["shots"]], tuple(sb["wan"]), job.id[-14:].replace("-", ""), lambda i: d / f"clip{i}.mp4", job.log)
    job.write("video/clips_timing.json", T); job.log("  clips: " + ", ".join(f"{k} {v}s" for k, v in T.items()))


def _dur(f): return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)]).decode().strip())


def xfade_filter(durations, xf, audio=True):
    """Filter graph that cross-dissolves N inputs (picture xfade, sound acrossfade). Returns (filter string, last video label, last audio label)."""
    vf, af = [], []; acc = durations[0]; vl, al = "0:v", "0:a"
    for k in range(1, len(durations)):
        vo, ao = f"v{k}", f"a{k}"
        vf.append(f"[{vl}][{k}:v]xfade=transition=fade:duration={xf}:offset={acc - xf:.3f}[{vo}]")
        if audio: af.append(f"[{al}][{k}:a]acrossfade=d={xf}[{ao}]")
        acc += durations[k] - xf; vl, al = vo, ao
    return ";".join(vf + af), vl, al


def assemble(job, cfg, caps):
    sb = job.read("video/storyboard.json"); d = vdir(job); v, pad = caps["video"], caps["padding"]; ow, oh = sb["out"]; lead = int(pad["lead_seconds"] * 1000); report = []

    narrated = sb.get("narrated", True)

    def seg_silent(s):                                              # a video without a voice: each clip at its natural speed, smoothed to the output frame rate, no audio track
        i = s["i"]; c = _dur(d / f"clip{i}.mp4"); out = d / f"seg{i}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(d / f"clip{i}.mp4"), "-vf", f"minterpolate=fps={v['out_fps']}:mi_mode=mci:mc_mode=aobmc:vsbmc=1,scale={ow}:{oh}:flags=lanczos", "-an",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(out)], check=True)
        return {"shot": i, "clip_s": round(c, 2), "slow": 1.0, "line_cut": False, "seg": out}

    def seg(s):
        if not narrated: return seg_silent(s)
        i = s["i"]; c = _dur(d / f"clip{i}.mp4"); a = _dur(d / f"say{i}.wav"); need = a + pad["lead_seconds"] + pad["tail_seconds"]
        slow = min(v["max_slow"], max(1.0, need / c)); total = c * slow; tempo = min(v["max_tempo"], max(1.0, need / total))          # slow the picture first, then speed the voice up slightly, never cut a line
        vf = f"setpts={slow:.4f}*PTS,minterpolate=fps={v['out_fps']}:mi_mode=mci:mc_mode=aobmc:vsbmc=1,scale={ow}:{oh}:flags=lanczos"
        af = f"atempo={tempo:.3f},adelay={lead}|{lead},loudnorm=I=-16:TP=-1.5:LRA=11,apad=whole_dur={total:.3f}"
        out = d / f"seg{i}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(d / f"clip{i}.mp4"), "-i", str(d / f"say{i}.wav"), "-filter_complex", f"[0:v]{vf}[v];[1:a]{af}[a]", "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", str(out)], check=True)
        return {"shot": i, "clip_s": round(c, 2), "audio_s": round(a, 2), "slow": round(slow, 3), "tempo": round(tempo, 3), "line_cut": (a / tempo + pad["lead_seconds"]) > total + 0.01, "seg": out}
    with ThreadPoolExecutor(10) as ex: report = list(ex.map(seg, sb["shots"]))
    segs = [r["seg"] for r in report]; fg, vl, al = xfade_filter([_dur(p) for p in segs], pad["crossfade_seconds"], audio=narrated); out = d / "video.mp4"
    if len(segs) == 1: subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(segs[0]), "-c", "copy", "-movflags", "+faststart", str(out)], check=True)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-y", *[x for p in segs for x in ("-i", str(p))], "-filter_complex", fg, "-map", f"[{vl}]", *(["-map", f"[{al}]"] if narrated else []), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                        *(["-c:a", "aac", "-b:a", "160k"] if narrated else ["-an"]), "-movflags", "+faststart", str(out)], check=True)
    cut = [r["shot"] for r in report if r["line_cut"]]
    if cut: job.log(f"  WARNING: narration of shot(s) {cut} runs past its clip and was cut")
    job.write("video.json", {"path": str(out), "seconds": round(_dur(out), 1), "mb": round(out.stat().st_size / 1e6, 1), "title": sb["title"], "cut_lines": cut,
                             "shots": [{k: v2 for k, v2 in r.items() if k != "seg"} for r in report]})
