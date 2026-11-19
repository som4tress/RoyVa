#!/usr/bin/env python3
"""Fails when code appears that can reach the shared 3090 box without being on the reviewed list. On 2026-11-17 that box reset abruptly six times while it was generating pictures, and the cause was still unknown after a day;
the least we can promise is that nothing reaches it that nobody has reviewed. Run by scripts/check.sh (so scripts/deploy.sh refuses to deploy a new door).
A "door" is any live code (not tests, not docs, not the manual scripts in scripts/remote that only the owner runs) that: posts a graph to ComfyUI ("/prompt"), names the box (its host name, its address, port 8188), uses ssh/scp, or calls ComfyUI's "/free".
To add a door on purpose: make sure it goes through img_video/guard.py (prompt ceiling + the shared GPU lock), record it in docs/handoff-*.md, then add the file to ALLOWED below."""
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "runtime", "jobs", "docs", "tests", "tools", "bench", ".pytest_cache"}
SKIP_PREFIX = ("scripts/remote/",)                       # manual scripts: they only run when the owner types them
EXT = (".py", ".mjs", ".js", ".sh", ".toml")
# pattern -> the files allowed to contain it (relative paths) and why
DOORS = {
    r"/prompt\b": {"what": "posting a graph to ComfyUI", "allowed": {
        "agents/img_video/img_video/comfy.py": "the agent's ComfyUI client (prompt ceiling in _call)", "agents/img_video/img_video/wan.py": "the agent's Wan client (same ceiling before it posts)",
        "agents/img_video/img_video/guard.py": "the ceiling itself",
        "bridge/opencode.mjs": "OpenCode's own session API, not ComfyUI", "bridge/bridge.mjs": "OpenCode's own session API, not ComfyUI", "gateway/royva_gateway/opencode_client.py": "OpenCode's own session API, not ComfyUI"}},
    r"8188|somdutta-linux|192\.168\.4\.55": {"what": "the box's address", "allowed": {
        "agents/img_video/config.toml": "the ONE place the 3090's address lives", "lares.toml": "voice transcription runs on the box (whisper_remote): an unguarded door, see the handoff",
        "lares.example.toml": "example text"}},
    r"\bssh\b|\bscp\b": {"what": "ssh/scp from live code", "allowed": {
        "bridge/whisper.mjs": "voice transcription over ssh to the box (no GPU lock): reviewed, see the handoff", "mcp/machine/machine.py": "the owner-only machine tool; [machine] hosts is empty in lares.toml",
        "scripts/lares_config.py": "config mapping", "lares.example.toml": "example text", "lares.toml": "config comment"}},
    r"""['"]/free['"]""": {"what": "ComfyUI /free (never: it caused host-RAM trouble on the box)", "allowed": {}},
}


def files(root):
    for d, dirs, names in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for n in names:
            if not n.endswith(EXT) or n.startswith("test_") or ".test." in n: continue
            rel = os.path.relpath(os.path.join(d, n), root)
            if not rel.startswith(SKIP_PREFIX): yield rel


def scan(root=ROOT):
    bad = []
    for rel in files(root):
        try: text = open(os.path.join(root, rel), encoding="utf-8", errors="replace").read()
        except OSError: continue
        for pat, info in DOORS.items():
            m = re.search(pat, text)
            if m and rel not in info["allowed"]:
                line = text.count("\n", 0, m.start()) + 1
                bad.append(f"{rel}:{line}: {info['what']} (matched {m.group(0)!r})")
    return bad


if __name__ == "__main__":
    bad = scan()
    if bad:
        print("NEW DOOR TO THE 3090 BOX, not on the reviewed list (tools/check_3090_doors.py):"); [print("  " + b) for b in bad]
        print("Route it through img_video/guard.py, record it in the handoff doc, then add it to ALLOWED."); sys.exit(1)
    print("3090 doors: only the reviewed ones")
