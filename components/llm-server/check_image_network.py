import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request

repo = 'rocm/vllm'
digest = 'sha256:2563fe42d9a90cd75c9e70ad223d68f9b83de1d4c4bb3f09c533d2cbd8044be0'
with urllib.request.urlopen(f'https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull', timeout=15) as r:
    token = json.load(r)['token']
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
opener = urllib.request.build_opener(NoRedirect)
request = urllib.request.Request(f'https://registry-1.docker.io/v2/{repo}/blobs/{digest}', headers={'Authorization': 'Bearer ' + token})
try:
    response = opener.open(request, timeout=15)
    response.close()
    raise RuntimeError('Expected a registry redirect')
except urllib.error.HTTPError as exc:
    if exc.code not in (302, 307):
        raise RuntimeError(f'Registry status {exc.code}') from None
    url = exc.headers['Location']
print('Registry data host:', urllib.parse.urlparse(url).hostname)
for family in ('-4', '-6'):
    result = subprocess.run(['curl', family, '-s', '--range', '0-1048575', '--connect-timeout', '5', '--max-time', '12', '-o', '/dev/null', '-w', '%{http_code} %{speed_download} bytes/sec', url], capture_output=True, text=True)
    print(family, result.stdout, 'exit', result.returncode)
