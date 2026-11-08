"""Gateway settings. Everything has a safe default; secrets come from the environment, never from files in this repo."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    registry_dir: Path = ROOT / "registry"
    state_dir: Path = ROOT.parent / "runtime" / "gateway"
    opencode_url: str = os.environ.get("ROYVA_OPENCODE_URL", "http://127.0.0.1:49380")
    opencode_password: str = os.environ.get("OPENCODE_SERVER_PASSWORD", "")
    opencode_dir: str = os.environ.get("ROYVA_OPENCODE_DIR", "/home/somdutta/RoyVa/runtime/workspace")
    router_url: str = os.environ.get("ROYVA_ROUTER_URL", "http://127.0.0.1:8203")
    router_name: str = os.environ.get("ROYVA_ROUTER_NAME", "9B+fs")          # "+fs" = few-shot prompt
    router_fallback_url: str = os.environ.get("ROYVA_ROUTER_FALLBACK_URL", "http://127.0.0.1:8100")
    router_fallback_name: str = os.environ.get("ROYVA_ROUTER_FALLBACK_NAME", "35B+fs")
    router_timeout_s: float = float(os.environ.get("ROYVA_ROUTER_TIMEOUT", "15"))
    users_file: Path = ROOT.parent / "runtime" / "gateway" / "users.json"                  # {"telegram:<id>": {"person": "...", "scopes": ["*"]}}
    token: str = os.environ.get("ROYVA_GATEWAY_TOKEN", "")                  # optional shared secret for /v1/*
    agent: str = os.environ.get("ROYVA_AGENT", "royva")
    max_concurrent_runs: int = int(os.environ.get("ROYVA_MAX_RUNS", "2"))
    expected_mcp: tuple[str, ...] = ("home-assistant", "gmail", "ha-history", "ha-entity-history", "ha-speakers", "ha-routines")
    home_location: str = os.environ.get("ROYVA_HOME_LOCATION", "")            # optional coarse place name, e.g. 'San Jose, CA'
    default_person: str = os.environ.get("ROYVA_DEFAULT_PERSON", "")   # HA person object id of the asking user; deployment config (scripts/env.sh), not code
    location_ttl_s: float = 60.0
    dynamic_context: dict = field(default_factory=dict)      # filled at startup from Home Assistant
    run_timeout_s: int = int(os.environ.get("ROYVA_RUN_TIMEOUT", "300"))
    poll_interval_s: float = 0.5
    # Tools that must never be granted by the router, whatever an intent says.
    never_grant: tuple[str, ...] = ("skill", "shell", "edit", "write", "read", "glob", "grep", "subagent", "execute", "question")
