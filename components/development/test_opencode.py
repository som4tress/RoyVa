import json
import os
from pathlib import Path
import subprocess
import time
import sys

root = Path.home() / 'llm-server'
environment = dict(os.environ)
for name in ('api.env', 'opencode.env'):
    for line in (root / name).read_text().splitlines():
        variable, value = line.split('=', 1)
        environment[variable] = value
started = time.perf_counter()
result = subprocess.run([
    str(Path.home() / '.opencode/bin/opencode'), 'run',
    *(['--server', 'http://127.0.0.1:49374'] if '--remote' in sys.argv else ['--standalone']), '--model', 'evo-agent/qwen36-agent',
    '--format', 'json', '--auto', '--title', 'EVO installation verification',
    'Use the shell tool to run hostname on this computer. Return only the hostname. Do not inspect or change any files.'
], cwd=Path.home() / 'OpenCodeRunner', env=environment, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
(root / 'opencode-test-output.jsonl').write_text(result.stdout)
(root / 'opencode-test-stderr.log').write_text(result.stderr)
report = {'exit_code': result.returncode, 'elapsed_seconds': round(time.perf_counter()-started, 2), 'hostname_in_output': 'somdutta-evo' in result.stdout}
(root / 'opencode-test-result.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report))
if result.returncode or not report['hostname_in_output']:
    raise SystemExit(1)
