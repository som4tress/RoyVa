"""Import checksum-verified public OCI layers into Docker's containerd store."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

root = Path('/home/somdutta/llm-server/image-layers').resolve(strict=True)
layers = json.loads((root / 'manifest.json').read_text())
for item in layers:
    digest = item['digest'].removeprefix('sha256:')
    if not re.fullmatch('[0-9a-f]{64}', digest):
        raise RuntimeError('Invalid registry layer digest')
    target = (root / digest).resolve(strict=True)
    if target.parent != root or target.stat().st_size != item['size']:
        raise RuntimeError('Invalid registry layer path or size')
    with target.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
            raise RuntimeError('Layer checksum mismatch')
        stream.seek(0)
        result = subprocess.run([
            'ctr', '-n', 'moby', 'content', 'ingest',
            '--expected-digest', 'sha256:' + digest,
            '--expected-size', str(item['size']), 'evo-verified-' + digest,
        ], stdin=stream, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'Layer import failed: {digest[:12]}: {result.stderr}')
    print('Imported:', digest[:12], flush=True)
