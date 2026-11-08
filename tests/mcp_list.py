"""List tools of a stdio MCP server (read-only: initialize + tools/list). Usage: mcp_list.py <cmd> [args...]"""
import json, subprocess, sys, select, time

def rpc(p, obj):
    p.stdin.write((json.dumps(obj) + "\n").encode()); p.stdin.flush()

def read_until(p, want_id, timeout=30):
    end = time.time() + timeout
    buf = b""
    while time.time() < end:
        r, _, _ = select.select([p.stdout], [], [], 1)
        if not r:
            continue
        line = p.stdout.readline()
        if not line:
            break
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("id") == want_id:
            return o
    raise TimeoutError("no response for id %s" % want_id)

p = subprocess.Popen(sys.argv[1:], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
try:
    rpc(p, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "royva-probe", "version": "0"}}})
    read_until(p, 1)
    rpc(p, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    rpc(p, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = read_until(p, 2)["result"]["tools"]
    size = len(json.dumps(tools))
    print("%d tools, schema JSON %d chars (~%d tokens)" % (len(tools), size, size // 4))
    for t in tools:
        print(" -", t["name"], "|", (t.get("description") or "").replace("\n", " ")[:90])
finally:
    p.kill()
