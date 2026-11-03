import json
from pathlib import Path
import urllib.request

repo = 'rocm/vllm'
tag = 'rocm7.13.0_gfx1151_ubuntu24.04_py3.13_pytorch_2.10.0_vllm_0.19.1'
with urllib.request.urlopen(f'https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull', timeout=20) as r:
    token = json.load(r)['token']
headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.index.v1+json'}
def manifest(ref):
    req = urllib.request.Request(f'https://registry-1.docker.io/v2/{repo}/manifests/{ref}', headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)
data = manifest(tag)
if 'manifests' in data:
    selected = next(x for x in data['manifests'] if x['platform']['architecture'] == 'amd64' and x['platform']['os'] == 'linux')
    data = manifest(selected['digest'])
log = (Path.home() / 'llm-server/image-gfx1151.log').read_text()
remaining = 0
for layer in data['layers']:
    short = layer['digest'].split(':')[1][:12]
    done = any(f'{short}: {status}' in log for status in ('Download complete', 'Pull complete', 'Already exists'))
    if not done:
        remaining += layer['size']
        print(short, round(layer['size']/2**30, 2), 'GiB layer still downloading')
print('Total compressed image GiB:', round(sum(x['size'] for x in data['layers'])/2**30, 2))
print('Incomplete layers full size GiB (partially downloaded):', round(remaining/2**30, 2))
