"""Per-node timing of one ComfyUI job, read from its websocket progress events. Standard library only. Strictly best-effort and read-only: a failure here is recorded (`error`) and never
raises, so it can never change or break a video job. ComfyUI only sends a job's events to the client that queued it, so the graph must be posted with this probe's `cid`."""
import base64
import json
import os
import socket
import struct
import threading
import time
import uuid


def _connect(host, port, cid, timeout=5):
    s = socket.create_connection((host, port), timeout=timeout)
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET /ws?clientId={cid} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = s.recv(4096)
        if not chunk: raise ConnectionError("closed during the handshake")
        buf += chunk
    head, rest = buf.split(b"\r\n\r\n", 1)
    if b" 101 " not in head.split(b"\r\n")[0]: raise ConnectionError("websocket upgrade refused")
    return s, rest


def _frames(s, buf):
    def need(n):
        nonlocal buf
        while len(buf) < n:
            chunk = s.recv(65536)
            if not chunk: raise ConnectionError("websocket closed")
            buf += chunk
    while True:
        need(2); ln = buf[1] & 0x7F; off = 2
        if ln == 126: need(4); ln = struct.unpack(">H", buf[2:4])[0]; off = 4
        elif ln == 127: need(10); ln = struct.unpack(">Q", buf[2:10])[0]; off = 10
        need(off + ln); op, payload, buf = buf[0] & 0x0F, buf[off:off + ln], buf[off + ln:]
        yield op, payload


class Probe:
    def __init__(self, base):
        self.cid, self.events, self.ok, self.error, self._sock, self._stop = uuid.uuid4().hex, [], False, None, None, False
        self._base = base

    def start(self):
        try:
            host, port = self._base.replace("http://", "").rstrip("/").split(":")
            self._sock, rest = _connect(host, int(port), self.cid); self._sock.settimeout(None); self.ok = True       # blocking reads: ComfyUI can be silent for a minute while a model loads
            threading.Thread(target=self._loop, args=(rest,), daemon=True).start()
        except Exception as e:                                           # noqa: BLE001  best-effort: never break the job
            self.error = f"{type(e).__name__}: {e}"
        return self

    def _loop(self, rest):
        try:
            for op, payload in _frames(self._sock, rest):
                if self._stop or op == 8: break
                if op != 1: continue
                m = json.loads(payload.decode()); d = m.get("data") or {}
                self.events.append((time.time(), m.get("type"), d.get("prompt_id"), d.get("node"), d.get("value"), d.get("max")))
        except Exception as e:                                           # noqa: BLE001
            if not self._stop: self.error = f"{type(e).__name__}: {e}"

    def stop(self):
        self._stop = True
        try:
            if self._sock:
                try: self._sock.shutdown(socket.SHUT_RDWR)                  # wakes the reader thread out of its blocking read
                except OSError: pass
                self._sock.close()
        except OSError: pass


def summarize(wf, events, pid, t_submit, t_end):
    """Seconds per node class and per sampler, from (time, type, prompt_id, node, value, max) events of ONE job. Returns {} when nothing usable arrived."""
    ex = [(t, n) for t, ty, p, n, v, mx in events if ty == "executing" and p in (None, pid) and n is not None]
    if not ex: return {}
    cls = lambda n: (wf.get(str(n).split(":")[0]) or {}).get("class_type", "?")
    by_class, starts = {}, {}
    for i, (t, n) in enumerate(ex):
        end = ex[i + 1][0] if i + 1 < len(ex) else t_end
        by_class[cls(n)] = by_class.get(cls(n), 0.0) + (end - t); starts.setdefault(n, t)
    prog = {}
    for t, ty, p, n, v, mx in events:
        if ty == "progress" and p in (None, pid) and n is not None: prog.setdefault(n, []).append(t)
    samplers = []
    for n, t0 in starts.items():
        if not cls(n).startswith("KSampler") or n not in prog: continue
        ts = prog[n]; samplers.append({"node": n, "start": round(t0 - t_submit, 1), "to_first_step": round(ts[0] - t0, 1), "later_steps": [round(b - a, 1) for a, b in zip(ts, ts[1:])]})
    samplers.sort(key=lambda s: s["start"])
    raw = [(round(t - t_submit, 2), ty, str(n), cls(n) if n is not None else "") for t, ty, p, n, v, mx in events if ty in ("executing", "progress") and p in (None, pid)]       # for investigations, not logged by default
    return {"total": round(t_end - t_submit, 1), "queue_wait": round(ex[0][0] - t_submit, 1), "by_class": {k: round(v, 1) for k, v in by_class.items()}, "samplers": samplers, "raw": raw}


def describe(label, prof):
    """One log line: where a job's seconds went."""
    if not prof: return f"  profile {label}: no per-node timing (websocket unavailable)"
    top = ", ".join(f"{k} {v}" for k, v in sorted(prof["by_class"].items(), key=lambda kv: -kv[1])[:6])
    s = prof["samplers"]; txt = f"  profile {label}: total {prof['total']}s, waited {prof['queue_wait']}s before the first node | {top}"
    if s:
        first, rest = s[0], s[1:]
        txt += f" | first sampler: {first['to_first_step']}s to its first step"
        if rest: txt += f", the other {len(rest)}: {sum(x['to_first_step'] for x in rest) / len(rest):.1f}s each"
        later = [x for sp in s for x in sp["later_steps"]]
        if later: txt += f" | later steps {sum(later) / len(later):.1f}s each ({len(later)})"
    return txt
