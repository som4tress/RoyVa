"""Shared stdio loop for the MCP servers whose tools can run for a long time (img-video, image-gen, machine). Standard library only.

The problem it fixes: the servers used to read one JSON-RPC line at a time and run the tool inside that loop, so while a tool was running nothing was reading stdin.
When the owner pressed Stop, OpenCode aborted the tool call and (per the MCP spec) sent `notifications/cancelled` for it, but the server never saw it: the agent, the render or the
remote command kept running (a 2-minute video kept the 3090 busy for 3 more minutes after Stop, measured 2026-11-19).

What `serve(handle)` does:
* the main thread keeps reading stdin; `notifications/cancelled` sets a threading.Event for that request id at once;
* `tools/call` requests are run by ONE worker thread, in arrival order (exactly as serial as before: a second call still waits for the first, so lock-file logic in the tools is unchanged);
* tools ask `cancelled()` (or use `run()`, a drop-in for subprocess.run that kills the child's process group) to find out that they should stop;
* the reply of a cancelled call is dropped (the client stopped waiting; the spec says not to answer);
* when stdin closes (OpenCode restarted or died) every pending call is cancelled, so no orphan renders are left behind.
"""
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

_NEVER = threading.Event()
_local = threading.local()
_events = {}                      # JSON request id -> Event, for tools/call requests that are queued or running
_lock = threading.Lock()
_out_lock = threading.Lock()


def current():
    """The cancel Event of the tools/call being run by this thread (one that is never set when called from anywhere else)."""
    return getattr(_local, "event", None) or _NEVER


def cancelled():
    return current().is_set()


class _Out:
    """stdout that writes whole lines atomically from any thread and drops the output of a cancelled call."""
    def __init__(self, raw):
        self.raw = raw

    def write(self, s):
        *lines, rest = (getattr(_local, "buf", "") + s).split("\n")
        _local.buf = rest
        if lines and not cancelled():
            with _out_lock:
                self.raw.write("\n".join(lines) + "\n"); self.raw.flush()
        return len(s)

    def flush(self):
        pass

    def __getattr__(self, name):
        return getattr(self.raw, name)


def _key(request_id):
    return json.dumps(request_id)


LOG = Path(os.environ.get("ROYVA_MCP_CANCEL_LOG", Path(__file__).resolve().parents[1] / "runtime" / "gateway" / "mcp_cancel.log"))


def _note(text):
    """One line per cancel received, so a Stop can be traced afterwards (best effort, never raises)."""
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a") as f: f.write(f"{time.strftime('%F %T')} pid {os.getpid()} {os.path.basename(sys.argv[0])}: {text}\n")
    except OSError:
        pass


def _error(text):
    print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(text)[:200]}}), flush=True)


def serve(handle, stdin=None):
    """Reads JSON-RPC lines from stdin until it closes; `handle(msg)` prints its own replies (as the servers always did)."""
    stdin = stdin or sys.stdin
    sys.stdout = _Out(sys.stdout)
    jobs = queue.Queue()

    def worker():
        while True:
            msg, event = jobs.get()
            if msg is None:
                return
            _local.event = event
            try:
                if not event.is_set(): handle(msg)
            except Exception as e:                                           # noqa: BLE001
                _error(e)
            finally:
                _local.event = None
                with _lock: _events.pop(_key(msg.get("id")), None)

    thread = threading.Thread(target=worker, daemon=True); thread.start()
    for line in stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except ValueError as e:
            _error(e); continue
        method = msg.get("method")
        if method == "notifications/cancelled":
            with _lock: event = _events.get(_key((msg.get("params") or {}).get("requestId")))
            if event: event.set()
            _note(f"cancel for request {(msg.get('params') or {}).get('requestId')}: " + ("running or queued call stopped" if event else "no such call (already finished)"))
        elif method == "tools/call":
            event = threading.Event()
            with _lock: _events[_key(msg.get("id"))] = event
            jobs.put((msg, event))
        else:
            try: handle(msg)
            except Exception as e:                                           # noqa: BLE001
                _error(e)
    with _lock:
        for event in _events.values(): event.set()                           # the client is gone: stop whatever is running
    jobs.put((None, None)); thread.join(30)


def kill_group(proc, grace=3.0):
    """SIGTERM the child's process group, SIGKILL it if it is still there after `grace` seconds."""
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 5.0)):
        try: os.killpg(proc.pid, sig)
        except ProcessLookupError: return
        try: proc.wait(wait); return
        except subprocess.TimeoutExpired: continue


def run(argv, timeout=None, **kw):
    """subprocess.run that ends the child when the current tools/call is cancelled. Same arguments the servers use (capture_output, text, env, cwd, stdin);
    raises subprocess.TimeoutExpired like subprocess.run; after a cancel it returns the (negative) return code of the killed child, and the reply is dropped anyway."""
    if kw.pop("capture_output", False): kw["stdout"] = kw["stderr"] = subprocess.PIPE
    data = kw.pop("input", None)
    if data is not None: kw["stdin"] = subprocess.PIPE
    proc = subprocess.Popen(argv, start_new_session=True, **kw)
    started = time.time()
    while True:
        try:
            out, err = proc.communicate(input=data, timeout=0.5); data = None
            return subprocess.CompletedProcess(argv, proc.returncode, out, err)
        except subprocess.TimeoutExpired:
            data = None                                                    # communicate() has buffered the input: do not pass it again
            if cancelled():
                kill_group(proc); out, err = proc.communicate()
                return subprocess.CompletedProcess(argv, proc.returncode, out, err)
            if timeout is not None and time.time() - started > timeout:
                kill_group(proc); proc.communicate()
                raise subprocess.TimeoutExpired(argv, timeout)
