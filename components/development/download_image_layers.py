"""Download public registry layers with parallel byte ranges; verify SHA256."""
import concurrent.futures
import hashlib
import json
import os
import sys
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request

ROOT = Path.home() / 'llm-server/image-layers'
ROOT.mkdir(exist_ok=True)
REPO = 'rocm/vllm'
TAG = 'rocm7.13.0_gfx1151_ubuntu24.04_py3.13_pytorch_2.10.0_vllm_0.19.1'
with urllib.request.urlopen(f'https://auth.docker.io/token?service=registry.docker.io&scope=repository:{REPO}:pull', timeout=20) as r:
    token = json.load(r)['token']
headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.index.v1+json'}
def get_manifest(ref):
    req = urllib.request.Request(f'https://registry-1.docker.io/v2/{REPO}/manifests/{ref}', headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)
manifest = get_manifest(TAG)
if 'manifests' in manifest:
    manifest = get_manifest(next(x['digest'] for x in manifest['manifests'] if x['platform'].get('architecture') == 'amd64' and x['platform'].get('os') == 'linux'))
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
opener = urllib.request.build_opener(NoRedirect)
log = (ROOT.parent / 'image-gfx1151.log').read_text()
layers = []
for layer in manifest['layers']:
    digest = layer['digest'].split(':')[1]
    short = digest[:12]
    if any(f'{short}: {status}' in log for status in ('Download complete', 'Pull complete', 'Already exists')):
        continue
    layers.append(layer)
(ROOT / ('manifest-small.json' if '--small' in sys.argv else 'manifest.json')).write_text(json.dumps(layers, indent=2))
for layer in layers:
    if '--small' in sys.argv and layer['size'] > 2*1024**3:
        continue
    digest = layer['digest'].split(':')[1]
    size = layer['size']
    target = ROOT / digest
    if target.exists() and target.stat().st_size == size:
        with target.open('rb') as f:
            if hashlib.file_digest(f, 'sha256').hexdigest() == digest:
                print('Already verified:', digest[:12], flush=True)
                continue
    req = urllib.request.Request(f'https://registry-1.docker.io/v2/{REPO}/blobs/sha256:{digest}', headers={'Authorization': 'Bearer ' + token})
    try:
        with opener.open(req, timeout=30) as r:
            url = r.url
    except urllib.error.HTTPError as e:
        if e.code not in (302, 307):
            raise RuntimeError(f'Registry status {e.code}') from None
        url = e.headers['Location']
    partial = ROOT / (digest + '.partial')
    fd = os.open(partial, os.O_CREAT | os.O_RDWR | os.O_TRUNC, 0o600)
    os.ftruncate(fd, size)
    completed = 0
    lock = threading.Lock()
    start_time = time.monotonic()
    print('Downloading:', digest[:12], size, 'bytes', flush=True)
    def fetch(bounds):
        global completed
        start, stop = bounds
        for attempt in range(5):
            try:
                request = urllib.request.Request(url, headers={'Range': f'bytes={start}-{stop}', 'Accept-Encoding': 'identity'})
                with urllib.request.urlopen(request, timeout=45) as response:
                    if size > 8*1024*1024 and response.status != 206:
                        raise RuntimeError('Server ignored range request')
                    offset = start
                    while block := response.read(1024*1024):
                        if offset + len(block) > stop + 1:
                            raise RuntimeError('Response exceeds requested byte range')
                        os.pwrite(fd, block, offset)
                        offset += len(block)
                    if offset != stop + 1:
                        raise RuntimeError('Incomplete byte range')
                with lock:
                    completed += stop-start+1
                    elapsed = time.monotonic()-start_time
                    print(digest[:12], f'{completed/size:.0%}', f'{completed/2**20/elapsed:.1f} MiB/s', flush=True)
                return
            except Exception as exc:
                if attempt == 4:
                    raise RuntimeError(f'Range {start}-{stop} failed: {type(exc).__name__}') from None
                time.sleep(2*(attempt+1))
    chunk = 8*1024*1024
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            list(pool.map(fetch, [(x, min(size-1, x+chunk-1)) for x in range(0, size, chunk)]))
        os.fsync(fd)
    finally:
        os.close(fd)
    with partial.open('rb') as f:
        actual = hashlib.file_digest(f, 'sha256').hexdigest()
    if actual != digest:
        raise RuntimeError('SHA256 verification failed')
    partial.rename(target)
    print('VERIFIED:', digest, flush=True)
print('All missing layers verified.', flush=True)
