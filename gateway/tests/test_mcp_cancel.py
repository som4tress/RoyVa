"""Stop reaches the MCP tools: a notifications/cancelled kills what the tool started, the reply is dropped, the server stays usable, and calls stay serial (mcp/stdio_cancel.py)."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("ROYVA_MCP_CANCEL_LOG", os.path.join(tempfile.gettempdir(), "royva_test_mcp_cancel.log"))        # tests never write the real runtime log
SERVER = '''
import json, sys, time
sys.path.insert(0, %r)
import stdio_cancel

def handle(msg):
    if msg.get("method") != "tools/call":
        print(json.dumps({"jsonrpc": "2.0", "id": msg.get("id"), "result": {}}), flush=True); return
    a = msg["params"]["arguments"]
    p = stdio_cancel.run(["sleep", str(a["sleep"])], capture_output=True, text=True) if a.get("sleep") else None
    print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {"rc": p.returncode if p else 0, "cancelled": stdio_cancel.cancelled(), "n": a.get("n")}}), flush=True)

if __name__ == "__main__":
    stdio_cancel.serve(handle)
''' % str(ROOT / "mcp")


class Server:
    def __init__(self):
        self.dir = tempfile.TemporaryDirectory(); path = Path(self.dir.name) / "srv.py"; path.write_text(SERVER)
        self.p = subprocess.Popen([sys.executable, str(path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.lines = []; threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.p.stdout: self.lines.append(json.loads(line))

    def send(self, obj): self.p.stdin.write(json.dumps(obj) + "\n"); self.p.stdin.flush()
    def call(self, i, **args): self.send({"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": "t", "arguments": args}})
    def cancel(self, i): self.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": i}})

    def wait_for(self, i, seconds=10):
        end = time.time() + seconds
        while time.time() < end:
            for m in self.lines:
                if m.get("id") == i: return m
            time.sleep(0.05)

    def close(self):
        try: self.p.stdin.close()
        except OSError: pass
        try: self.p.wait(15)
        except subprocess.TimeoutExpired: self.p.kill()
        self.dir.cleanup()


def sleeping(marker):
    out = subprocess.run(["pgrep", "-fx", f"sleep {marker}"], capture_output=True, text=True).stdout.split()
    return bool(out)


def test_cancel_kills_the_running_child_and_drops_the_reply_and_the_server_stays_usable():
    s = Server()
    try:
        s.call(2, sleep="61.37"); time.sleep(1.5); assert sleeping("61.37")
        t0 = time.time(); s.cancel(2)
        end = time.time() + 8
        while sleeping("61.37") and time.time() < end: time.sleep(0.1)
        assert not sleeping("61.37"), "the child was still running after the cancel"
        assert time.time() - t0 < 6
        s.call(3, n="after"); r = s.wait_for(3); assert r and r["result"]["n"] == "after" and r["result"]["cancelled"] is False
        assert not any(m.get("id") == 2 for m in s.lines), "a cancelled call must not be answered"
    finally: s.close()


def test_calls_stay_serial_and_a_queued_call_can_be_cancelled_before_it_starts():
    s = Server()
    try:
        s.call(1, sleep="1.1", n="first"); s.call(2, sleep="61.38", n="second"); s.call(3, n="third")
        time.sleep(0.3); s.cancel(2)                                            # 2 has not started: it must never start
        assert s.wait_for(1)["result"]["n"] == "first"
        assert s.wait_for(3)["result"]["n"] == "third"
        assert not sleeping("61.38") and not any(m.get("id") == 2 for m in s.lines)
        ids = [m["id"] for m in s.lines]; assert ids == [1, 3]                  # replies come in the order the calls arrived
    finally: s.close()


def test_closing_stdin_cancels_what_is_running():
    s = Server()
    s.call(5, sleep="61.39"); time.sleep(1.5); assert sleeping("61.39")
    s.p.stdin.close(); s.p.wait(20)
    assert not sleeping("61.39")
    s.dir.cleanup()


def test_other_requests_are_answered_while_a_tool_runs():
    s = Server()
    try:
        s.call(1, sleep="2.2"); time.sleep(0.4)
        s.send({"jsonrpc": "2.0", "id": 9, "method": "tools/list"})
        assert s.wait_for(9, 1.5) is not None                                    # the reader is not blocked by the running tool
        assert s.wait_for(1) is not None
    finally: s.close()


def test_run_is_a_drop_in_for_subprocess_run():
    sys.path.insert(0, str(ROOT / "mcp")); import stdio_cancel
    r = stdio_cancel.run(["cat"], input="hello", capture_output=True, text=True, timeout=10); assert (r.returncode, r.stdout) == (0, "hello")
    r = stdio_cancel.run(["sh", "-c", "echo out; echo err >&2; exit 3"], capture_output=True, timeout=10, stdin=subprocess.DEVNULL); assert (r.returncode, r.stdout, r.stderr) == (3, b"out\n", b"err\n")
    try: stdio_cancel.run(["sleep", "30"], timeout=1); raise AssertionError("no timeout")
    except subprocess.TimeoutExpired: pass
