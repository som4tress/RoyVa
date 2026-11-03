"""Fetch pinned public safetensor shards with ranges and verify their LFS hashes."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import urllib.request
from huggingface_hub import HfApi, hf_hub_url

repo = 'Minachist/Qwen3.6-35B-A3B-INT8-AutoRound'
revision = '5d75e401e3f2f1e88ae997dc7a98bf7581313a17'
root = Path.home() / 'llm-server/int8-candidate'
required = set(json.loads((root / 'model.safetensors.index.json').read_text())['weight_map'].values())
info = HfApi().model_info(repo, revision=revision, files_metadata=True)
files = [f for f in info.siblings if f.rfilename in required]
if {f.rfilename for f in files} != required:
    raise RuntimeError('Model index references missing shards')
(root / 'download-provenance.json').write_text(json.dumps({'repo': repo, 'revision': revision, 'files': [{'name': f.rfilename, 'size': f.size, 'sha256': f.lfs.sha256} for f in files]}, indent=2))
for file in files:
    if Path(file.rfilename).name != file.rfilename:
        raise RuntimeError('Unexpected shard path')
    target = root / file.rfilename
    if target.exists() and target.stat().st_size == file.size:
        with target.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() == file.lfs.sha256:
                print('Already verified:', file.rfilename, flush=True)
                continue
    url = hf_hub_url(repo, file.rfilename, revision=revision)
    request = urllib.request.Request(url, headers={'Range': 'bytes=0-0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        data_url = response.url
    partial = root / (file.rfilename + '.partial')
    fd = os.open(partial, os.O_CREAT | os.O_RDWR | os.O_TRUNC, 0o600)
    os.ftruncate(fd, file.size)
    done = 0
    lock = threading.Lock()
    started = time.monotonic()
    print('Downloading:', file.rfilename, file.size, 'bytes', flush=True)
    def fetch(bounds):
        global done
        start, stop = bounds
        for attempt in range(5):
            try:
                req = urllib.request.Request(data_url, headers={'Range': f'bytes={start}-{stop}', 'Accept-Encoding': 'identity'})
                with urllib.request.urlopen(req, timeout=45) as response:
                    if response.status != 206:
                        raise RuntimeError('Server ignored range request')
                    offset = start
                    while block := response.read(1024*1024):
                        if offset + len(block) > stop+1:
                            raise RuntimeError('Range exceeded requested size')
                        os.pwrite(fd, block, offset)
                        offset += len(block)
                    if offset != stop+1:
                        raise RuntimeError('Incomplete range')
                with lock:
                    done += stop-start+1
                    elapsed = time.monotonic()-started
                    print(file.rfilename, f'{100*done/file.size:.1f}%', f'{done/2**20/elapsed:.1f} MiB/s', flush=True)
                return
            except Exception as exc:
                if attempt == 4:
                    raise RuntimeError(f'Range failed: {type(exc).__name__}') from None
                time.sleep(2*(attempt+1))
    chunk = 8*1024*1024
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=64) as pool:
            list(pool.map(fetch, [(x, min(file.size-1, x+chunk-1)) for x in range(0, file.size, chunk)]))
        os.fsync(fd)
    finally:
        os.close(fd)
    with partial.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != file.lfs.sha256:
        raise RuntimeError('Shard SHA256 mismatch')
    partial.rename(target)
    print('VERIFIED:', file.rfilename, actual, flush=True)
print('All model shards verified.', flush=True)
