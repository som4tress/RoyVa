#!/usr/bin/env python3
"""Read the deployment config (lares.toml) and print shell `export` lines. Used by scripts/env.sh.

Precedence: an environment variable that is already set wins; then lares.toml; then the built-in default.
No config file is fine: the defaults apply. A malformed file is an error (exit 2), never silently ignored.
"""
import os
import shlex
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTS = {"product": "Lares", "assistant_name": "Roy", "command": "roy"}

# (toml section, key) -> environment variable
MAP = {
    ("brand", "product"): "LARES_PRODUCT",
    ("brand", "assistant_name"): "LARES_ASSISTANT_NAME",
    ("brand", "command"): "LARES_COMMAND",
    ("household", "default_person"): "ROYVA_DEFAULT_PERSON",
    ("household", "protected_devices"): "ROYVA_PROTECTED_DEVICES",
    ("remote", "hosts"): "ROYVA_REMOTE_HOSTS",
    ("voice", "whisper_remote"): "WHISPER_REMOTE",
    ("paths", "node_bin"): "LARES_NODE_BIN",
    ("paths", "llm_server"): "LARES_LLM_DIR",
    ("paths", "opencode_bin"): "LARES_OPENCODE_BIN",
    ("paths", "telegram_env"): "LARES_TELEGRAM_ENV",
}


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def exports(cfg: dict, env: dict) -> list[str]:
    out = []
    for (section, key), var in MAP.items():
        if var in env:
            continue
        value = cfg.get(section, {}).get(key)
        if value is None and section == "brand":
            value = DEFAULTS[key]
        if value is None:
            continue
        if isinstance(value, list):
            value = ",".join(str(v) for v in value)
        out.append(f"export {var}={shlex.quote(str(value))}")
    return out


def main() -> int:
    path = Path(os.environ.get("LARES_CONFIG") or ROOT / "lares.toml")
    try:
        cfg = load(path)
    except tomllib.TOMLDecodeError as e:
        print(f"echo 'lares.toml is invalid: {e}' >&2; false", end="")
        sys.stderr.write(f"lares_config: {path}: {e}\n")
        return 2
    print("\n".join(exports(cfg, os.environ)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
