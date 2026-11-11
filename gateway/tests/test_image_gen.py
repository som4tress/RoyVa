"""image door: input validation, photo-path restriction, size parsing, dry run and the subprocess command. sd-cli is never really run (subprocess is faked)."""
import importlib.util
import os
import struct
import zlib
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("image_gen", Path(__file__).resolve().parents[2] / "mcp" / "image" / "image_gen.py")
g = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(g)


def png(path, w, h):
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * w for _ in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@pytest.fixture
def env(tmp_path, monkeypatch):
    for n in ("diffusion", "llm", "vae"):
        (tmp_path / "models").mkdir(exist_ok=True)
    models = tmp_path / "models"
    for f in list(g.FILES.values()) + [g.VISION]:
        (models / f).write_bytes(b"x")
    (tmp_path / "sd").mkdir()
    (tmp_path / "sd" / "sd-cli").write_bytes(b"x")
    monkeypatch.setattr(g, "MODELS", models)
    monkeypatch.setattr(g, "SD_DIR", tmp_path / "sd")
    monkeypatch.setattr(g, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(g, "INBOX", tmp_path / "inbox")
    monkeypatch.setattr(g, "LOCK", tmp_path / "image.lock")
    monkeypatch.setattr(g, "DRY_FLAG", tmp_path / "nodry")
    monkeypatch.delenv("ROYVA_DRY_RUN", raising=False)
    (tmp_path / "inbox").mkdir()
    calls = []

    class Done:
        returncode, stdout, stderr = 0, "", ""

    def fake_run(cmd, **kw):
        calls.append(cmd)
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"P" * 5000)
        return Done()

    monkeypatch.setattr(g.subprocess, "run", fake_run)
    return tmp_path, calls


def test_generate_builds_command_and_returns_picture(env):
    _, calls = env
    r = g.generate_image({"prompt": "a sloth", "width": 1280, "height": 704, "steps": 99})
    assert r["ok"] and Path(r["image_path"]).exists() and r["image_path"].startswith(str(g.OUT_DIR))
    cmd = calls[0]
    assert cmd[cmd.index("--steps") + 1] == str(g.MAX_STEPS) and "-r" not in cmd
    assert cmd[cmd.index("-W") + 1] == "1280" and cmd[cmd.index("-H") + 1] == "704"


@pytest.mark.parametrize("args", [{"prompt": ""}, {"prompt": "x" * 2000}, {"prompt": "a", "width": 1000}, {"prompt": "a", "height": 64}])
def test_generate_rejects_bad_input(env, args):
    try:
        r = g.generate_image(args)
    except ValueError:
        return
    assert r["ok"] is False


def test_dry_run_does_nothing(env, monkeypatch):
    _, calls = env
    monkeypatch.setenv("ROYVA_DRY_RUN", "1")
    assert "DRY RUN" in g.generate_image({"prompt": "a"})["did"] and not calls


def test_busy_lock_is_reported(env):
    import fcntl
    with open(g.LOCK, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        assert "still being generated" in g.generate_image({"prompt": "a"})["error"]


def test_edit_only_reads_photos_from_the_inbox(env):
    tmp, calls = env
    outside = tmp / "secret.png"
    png(outside, 64, 64)
    assert g.edit_image({"image": str(outside), "prompt": "ghibli"})["ok"] is False
    assert g.edit_image({"image": str(tmp / "inbox" / ".." / "secret.png"), "prompt": "ghibli"})["ok"] is False
    assert g.edit_image({"image": str(tmp / "inbox" / "nope.png"), "prompt": "ghibli"})["ok"] is False
    assert g.edit_image({"image": "/etc/passwd", "prompt": "x"})["ok"] is False and not calls


def test_edit_passes_reference_and_vision_and_scales_size(env):
    tmp, calls = env
    photo = tmp / "inbox" / "p.png"
    png(photo, 2000, 1000)
    r = g.edit_image({"image": str(photo), "prompt": "Turn this into a Ghibli painting"})
    assert r["ok"] and "image_path" in r
    cmd = calls[0]
    assert cmd[cmd.index("-r") + 1] == str(photo) and cmd[cmd.index("--llm_vision") + 1].endswith(g.VISION)
    assert (cmd[cmd.index("-W") + 1], cmd[cmd.index("-H") + 1]) == ("1024", "512")


def test_edit_needs_the_vision_file(env):
    tmp, _ = env
    (g.MODELS / g.VISION).unlink()
    photo = tmp / "inbox" / "p.png"
    png(photo, 64, 64)
    assert "vision file" in g.edit_image({"image": str(photo), "prompt": "x"})["error"]


def test_size_reads_png(tmp_path):
    p = tmp_path / "a.png"
    png(p, 300, 200)
    assert g._size(p) == (300, 200)
