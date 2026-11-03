"""Print health, models, and memory without displaying credentials."""
import base64
import json
from pathlib import Path
import urllib.request
import urllib.error

root = Path.home() / 'llm-server'
key = (root / 'api.env').read_text().strip().split('=', 1)[1]
password = (root / 'opencode.env').read_text().strip().split('=', 1)[1]
for port, path, auth in [
    (49374, '/api/info', 'Basic ' + base64.b64encode(('opencode:' + password).encode()).decode()),
    (8000, '/v1/models', 'Bearer ' + key),
    (8001, '/v1/models', 'Bearer ' + key),
]:
    request = urllib.request.Request(f'http://127.0.0.1:{port}{path}', headers={'Authorization': auth})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.load(response)
            if port == 49374:
                print('OpenCode:', response.status, 'authenticated response received')
            else:
                print(port, response.status, json.dumps(body))
    except Exception as exc:
        print(port, type(exc).__name__, str(exc))
