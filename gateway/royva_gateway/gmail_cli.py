"""Command line for per-person Gmail enrollment (see gmail_enroll.py)."""
from __future__ import annotations

import sys
from pathlib import Path

from .config import Settings
from .gmail_enroll import EnrollError, Enroller

CONFIG = Path(__file__).resolve().parents[2] / "config" / "opencode.json"


def main(argv: list[str]) -> int:
    e = Enroller(Settings().state_dir)
    cmd = argv[0] if argv else ""
    try:
        if cmd == "start" and len(argv) in (2, 3):
            print(e.start(argv[1], manage="--manage" in argv[2:])); print("Open the link, sign in, then run:  royva-gmail finish '<code shown on the page>'", file=sys.stderr)
        elif cmd == "finish" and len(argv) >= 2:
            r = e.finish(" ".join(argv[1:])); e.sync_opencode_config(CONFIG)
            print(f"Connected {r['email']} as '{r['person']}'. Restart OpenCode to load the new Gmail servers, then set \"mail\": \"{r['person']}\" for the user in users.json.")
        elif cmd == "list":
            for p, a in e.accounts().items():
                print(f"{p}\t{a['email']}")
        elif cmd == "revoke" and len(argv) == 2:
            ok = e.revoke(argv[1]); e.sync_opencode_config(CONFIG); print("revoked (restart OpenCode)" if ok else "no such person")
        else:
            print(__doc__.strip() + "\nusage: royva-gmail start <person> [--manage] | finish <code> | list | revoke <person>", file=sys.stderr); return 2
    except EnrollError as ex:
        print(f"error: {ex}", file=sys.stderr); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
