import sys
import time
import urllib.request

port = int(sys.argv[1])
deadline = time.monotonic() + 850
while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3) as response:
            if response.status == 200:
                print(f'Model endpoint on {port} is ready.', flush=True)
                break
    except Exception:
        pass
    time.sleep(2)
else:
    raise SystemExit(f'Model endpoint on {port} did not become ready.')
