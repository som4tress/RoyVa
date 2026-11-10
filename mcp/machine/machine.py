"""MCP server (stdio, newline JSON-RPC): run shell commands on this machine and on allowlisted remote machines.
Read/write is decided by the operating system, not by looking at the command:
  run / remote_run                 - the command runs inside a read-only bubblewrap sandbox (whole filesystem read-only, throwaway /tmp, no network,
                                     own process namespace, no service sockets, clean environment, credential files hidden). A read just works; a write fails with
                                     "Read-only file system" and the result tells the model to use the approved tool.
  run_approved / remote_run_approved - the same command for real. Registered as always-ask tools: the owner sees the exact command and approves it first.
Never root (sudo/su are refused), timeouts and output caps on everything, every command is logged. Honors the dry-run flag."""
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
ROOT = Path(__file__).resolve().parents[2]
LOG = Path(os.environ.get("ROYVA_MACHINE_LOG", ROOT / "runtime" / "gateway" / "machine.log"))
DRY_FLAG = Path(os.environ.get("ROYVA_DRY_RUN_FLAG", ROOT / "runtime" / "gateway" / "dry_run"))
MAX_CMD = 3000                                   # an approval must show the whole command, so longer ones are refused
MAX_OUT = 20000
DEFAULT_TIMEOUT, MAX_TIMEOUT = 30, 120
SAFE_PATH = "/usr/local/bin:/usr/bin:/bin"
ROOT_CMD = re.compile(r"(^|[;&|(`\s/])(sudo|su|doas|pkexec)(\s|$)")
WRITE_HINT = re.compile(r"Read-only file system|Permission denied|Operation not permitted|cannot create|cannot touch|Cannot open", re.I)
# Home paths that hold secrets: emptied or blanked inside the sandbox (only those that exist are mounted).
HIDE_DIRS = [".ssh", ".gnupg", ".gmail-mcp", ".royva", ".aws", ".kube", ".docker", ".config/gh", ".config/opencode", ".config/gcloud",
             ".local/share/opencode", ".local/share/keyrings", ".claude", "RoyVa/runtime/gateway/gmail", "RoyVa/runtime/state", "RoyVa/runtime/gateway/users.json", "RoyVa/runtime/gateway/invites.json"]
HIDE_FILES = [".netrc", ".npmrc", ".git-credentials", "llm-server/ha-remote.json", "llm-server/api.env", "llm-server/ha.env", "RoyVa/runtime/server.env", "OpenRouter.txt", "OpenAI.txt", ".claude.json"]
# A few exact read-only commands that cannot run inside the sandbox (they need the host's privileges or process list). Matched token for token.
TRUSTED_EXACT = {("crontab", "-l"), ("systemctl", "list-timers", "--all"), ("systemctl", "--user", "list-timers", "--all"),
                 ("ps", "-eo", "pid,ppid,etime,pcpu,pmem,comm")}


def hosts() -> list:
    return [h.strip() for h in os.environ.get("ROYVA_REMOTE_HOSTS", "").split(",") if h.strip()]


def refuse(command: str):
    if not isinstance(command, str) or not command.strip():
        return "empty command"
    if len(command) > MAX_CMD:
        return f"command is longer than {MAX_CMD} characters; the owner must be able to review it in full, so split it into smaller steps"
    if "\x00" in command:
        return "invalid command"
    if ROOT_CMD.search(command):
        return "root is not available. Do not use sudo or su: tell the owner the command to run themselves"
    return None


SECRET_NAME = re.compile(r"(\.env$|^\.env|credential|secret|token(?!iz)|^id_(rsa|ed25519|ecdsa|dsa)|\.(pem|key|p12|pfx|jks)$|^auth\.json$|^\.(netrc|npmrc|pgpass|git-credentials)$|api[_-]?key|password|passwd)", re.I)
SKIP_DIRS = {".venv", "node_modules", ".cache", ".nvm", ".git", "snap", "site-packages", "__pycache__", ".npm", ".cargo", ".rustup"}
_scan = {"home": None, "at": 0.0, "files": []}


def secret_files(home: Path = HOME, max_depth: int = 5, ttl: float = 60.0) -> list:
    """Files under the home directory whose NAME looks like a secret (.env, credentials, tokens, keys...). Found by pattern, not a fixed list, so a new
    secret file is covered without an edit here. Public keys and tokenizer files are not secrets. Cached for a minute."""
    now = time.time()
    if _scan["home"] == str(home) and now - _scan["at"] < ttl:
        return _scan["files"]
    found = []
    base = str(home).rstrip("/").count("/")
    for dirpath, dirs, files in os.walk(home, followlinks=False):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and dirpath.count("/") - base < max_depth]
        for f in files:
            if f.endswith(".pub") or not SECRET_NAME.search(f):
                continue
            p = os.path.join(dirpath, f)
            if os.path.isfile(p) and not os.path.islink(p):
                found.append(p)
    _scan.update(home=str(home), at=now, files=found)
    return found


def sandbox_argv(home: Path = HOME) -> list:
    """bwrap arguments for a read-only sandbox; mounts only the secret paths that exist on this machine."""
    a = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--tmpfs", "/run",
         "--clearenv", "--setenv", "PATH", SAFE_PATH, "--setenv", "HOME", str(home), "--setenv", "LANG", "C.UTF-8",
         "--unshare-pid", "--unshare-net", "--unshare-ipc", "--unshare-uts", "--die-with-parent", "--new-session"]
    for d in HIDE_DIRS:
        if (home / d).is_dir():
            a += ["--tmpfs", str(home / d)]
    covered = [str(home / d) + "/" for d in HIDE_DIRS]
    for f in dict.fromkeys([str(home / f) for f in HIDE_FILES if (home / f).is_file()] + secret_files(home)):
        if not any(f.startswith(c) for c in covered):                          # already inside a hidden directory
            a += ["--ro-bind", "/dev/null", f]
    return a


def clean_env() -> dict:
    """The environment of the process that launches bwrap: its /proc/1/environ is visible inside the sandbox, so it must hold nothing secret."""
    return {"PATH": SAFE_PATH, "HOME": str(HOME), "LANG": "C.UTF-8", "USER": os.environ.get("USER", ""), "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}"}


REMOTE_HIDE = [".ssh", ".gnupg", ".config/gh", ".aws", ".kube"]


def remote_command(command: str, sandboxed: bool) -> str:
    """The single string ssh hands to the remote login shell. Quoting is done once, with shlex, so nothing in the user's command can break out of it."""
    if not sandboxed:
        return f"sh -c {shlex.quote(command)}"
    flags = ("--ro-bind / / --dev /dev --proc /proc --tmpfs /tmp --tmpfs /run --clearenv --setenv PATH /usr/local/bin:/usr/bin:/bin --setenv HOME \"$HOME\" "
             "--setenv LANG C.UTF-8 --unshare-pid --unshare-net --unshare-ipc --unshare-uts --die-with-parent --new-session")
    hide = " ".join(f'"$HOME/{d}"' for d in REMOTE_HIDE)
    script = (f'set --; for d in {hide}; do [ -d "$d" ] && set -- "$@" --tmpfs "$d"; done; '
              f"exec bwrap {flags} \"$@\" -- sh -c {shlex.quote(command)}")
    return f"sh -c {shlex.quote(script)}"


def _log(rec: dict) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **rec}) + "\n")
    except OSError:
        pass


def _cap(text: bytes) -> str:
    s = text.decode("utf-8", "replace")
    return s if len(s) <= MAX_OUT else s[:MAX_OUT] + f"\n[output cut at {MAX_OUT} characters]"


def _exec(argv, env, timeout, cwd=None, runner=subprocess.run) -> dict:
    try:
        p = runner(argv, env=env, cwd=cwd, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "error": f"timed out after {timeout}s"}
    except FileNotFoundError as e:                       # e.g. bwrap or ssh missing: never fall back to running without the sandbox
        return {"exit_code": None, "error": f"cannot run: {e.filename or argv[0]} is not installed on this machine"}
    return {"exit_code": p.returncode, "stdout": _cap(p.stdout), "stderr": _cap(p.stderr)}


def _timeout(args) -> int:
    try:
        return max(1, min(int(args.get("timeout") or DEFAULT_TIMEOUT), MAX_TIMEOUT))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT


def _with_hint(res: dict, approved_tool: str) -> dict:
    if WRITE_HINT.search(res.get("stderr", "")):                      # a failed write inside a longer command still ends with exit 0
        res["hint"] = (f"This ran in a read-only sandbox. If the command only needs to read something outside it, try another way (for example /etc/cron* and "
                       f"~/.config/systemd/user/*.timer for scheduled jobs). If it really needs to change something, call {approved_tool} with the same command: the owner approves it first.")
    return res


def run(args, runner=subprocess.run) -> dict:
    command = args.get("command")
    bad = refuse(command)
    if bad:
        return {"error": bad}
    t = _timeout(args)
    try:
        trusted = tuple(shlex.split(command)) in TRUSTED_EXACT
    except ValueError:
        trusted = False
    argv = shlex.split(command) if trusted else sandbox_argv() + ["--", "sh", "-c", command]
    res = _exec(argv, clean_env(), t, runner=runner)
    res["sandbox"] = not trusted
    _log({"tool": "run", "command": command, "rc": res.get("exit_code"), "sandbox": not trusted})
    return _with_hint(res, "run_approved")


def run_approved(args, runner=subprocess.run) -> dict:
    command = args.get("command")
    bad = refuse(command)
    if bad:
        return {"error": bad}
    if os.environ.get("ROYVA_DRY_RUN") == "1" or DRY_FLAG.exists():
        return {"dry_run": True, "did": f"[DRY RUN, nothing happened] {command}"}
    res = _exec(["/bin/bash", "-c", command], clean_env(), _timeout(args), cwd=str(HOME), runner=runner)
    _log({"tool": "run_approved", "command": command, "rc": res.get("exit_code")})
    return res


def _remote(args, sandboxed: bool, runner) -> dict:
    command, host = args.get("command"), str(args.get("host") or "")
    bad = refuse(command)
    if bad:
        return {"error": bad}
    if host not in hosts():
        return {"error": f"host not allowed. Allowed hosts: {', '.join(hosts()) or 'none configured'}"}
    if not sandboxed and (os.environ.get("ROYVA_DRY_RUN") == "1" or DRY_FLAG.exists()):
        return {"dry_run": True, "did": f"[DRY RUN, nothing happened] on {host}: {command}"}
    argv = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=yes", host, remote_command(command, sandboxed)]
    res = _exec(argv, clean_env(), _timeout(args), runner=runner)
    _log({"tool": "remote_run" if sandboxed else "remote_run_approved", "host": host, "command": command, "rc": res.get("exit_code")})
    return _with_hint(res, "remote_run_approved") if sandboxed else res


def remote_run(args, runner=subprocess.run) -> dict:
    return {**_remote(args, True, runner), "sandbox": True}


def remote_run_approved(args, runner=subprocess.run) -> dict:
    return _remote(args, False, runner)


CMD = {"type": "string", "description": "A shell command (max 3000 characters)."}
TIMEOUT = {"type": "integer", "description": "Seconds before it is stopped (default 30, max 120)."}
HOST = {"type": "string", "description": "An allowed remote host, as user@host."}
TOOLS = [
    {"name": "run", "description": "Run a shell command on THIS machine in a read-only sandbox (no network, no root, secrets hidden). Reading works: files, free memory, disk, logs, scheduled jobs. "
                                   "A command that tries to change anything fails with 'Read-only file system'; then use run_approved.",
     "inputSchema": {"type": "object", "properties": {"command": CMD, "timeout": TIMEOUT}, "required": ["command"], "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}},
    {"name": "run_approved", "description": "Run a shell command on THIS machine for real, so it can change things. The owner approves the exact command first. Use only after run showed it needs to write.",
     "inputSchema": {"type": "object", "properties": {"command": CMD, "timeout": TIMEOUT}, "required": ["command"], "additionalProperties": False},
     "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False}},
    {"name": "remote_run", "description": "Run a shell command on an allowed REMOTE machine (over ssh) in a read-only sandbox there. Reading works; a command that tries to change anything fails; then use remote_run_approved.",
     "inputSchema": {"type": "object", "properties": {"host": HOST, "command": CMD, "timeout": TIMEOUT}, "required": ["host", "command"], "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}},
    {"name": "remote_run_approved", "description": "Run a shell command on an allowed REMOTE machine for real, so it can change things there. The owner approves the exact command and host first.",
     "inputSchema": {"type": "object", "properties": {"host": HOST, "command": CMD, "timeout": TIMEOUT}, "required": ["host", "command"], "additionalProperties": False},
     "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True}},
]
FUNCS = {"run": run, "run_approved": run_approved, "remote_run": remote_run, "remote_run_approved": remote_run_approved}


def handle(msg):
    method, ident = msg.get("method"), msg.get("id")
    if method == "initialize":
        result = {"protocolVersion": msg.get("params", {}).get("protocolVersion", "2025-03-26"), "capabilities": {"tools": {}},
                  "serverInfo": {"name": "machine", "version": "1.0.0"}}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        p = msg.get("params", {})
        try:
            result = {"content": [{"type": "text", "text": json.dumps(FUNCS[p.get("name")](p.get("arguments", {})))}]}
        except Exception as e:                                          # noqa: BLE001
            result = {"content": [{"type": "text", "text": json.dumps({"error": str(e)[:300]})}], "isError": True}
    elif ident is None:
        return
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": "Method not found"}}), flush=True)
        return
    print(json.dumps({"jsonrpc": "2.0", "id": ident, "result": result}), flush=True)


if __name__ == "__main__":
    for line in sys.stdin:
        if line.strip():
            try:
                handle(json.loads(line))
            except Exception as e:                                      # noqa: BLE001
                print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)[:200]}}), flush=True)
