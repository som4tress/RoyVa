"""Loads config.toml and capabilities.json; any config value can be overridden by IMG_VIDEO_<SECTION>_<KEY>."""
import json
import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _coerce(old, new: str):
    if isinstance(old, bool): return new.lower() in ("1", "true", "yes")
    if isinstance(old, int): return int(new)
    if isinstance(old, float): return float(new)
    return new


def load():
    cfg = tomllib.loads((ROOT / "config.toml").read_text())
    for sec, vals in cfg.items():
        for k, v in vals.items():
            env = os.environ.get(f"IMG_VIDEO_{sec}_{k}".upper())
            if env is not None: vals[k] = _coerce(v, env)
    caps = json.loads((ROOT / "capabilities.json").read_text())
    return cfg, caps


def cap(caps, *path):
    """caps['tts_chars_per_second'] -> 18.2 (entries are either a bare value or {'value':..., 'source':...})."""
    v = caps
    for p in path: v = v[p]
    return v["value"] if isinstance(v, dict) and "value" in v else v


def jobs_dir(cfg) -> Path:
    p = Path(os.path.expanduser(cfg["paths"]["jobs"]))
    return p if p.is_absolute() else ROOT / p
