#!/usr/bin/env python3
"""Capture deployed source without modifying it; --check detects drift."""
import argparse, hashlib, json, os, re, subprocess
from pathlib import Path

HOME = Path.home()
ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.git','node_modules','__pycache__','.venv','venv','dist','build',
        '.expo','.next','.cache','cache','torch_compile_cache','coverage','.gradle','Pods','target','bundle'}
EXT = {'.py','.mjs','.cjs','.js','.jsx','.ts','.tsx','.sh','.ps1','.md',
       '.json','.toml','.yaml','.yml','.css','.html','.xml','.plist','.lock',
       '.patch','.service','.conf','.txt','.sql','.swift','.kt','.java',
       '.gradle','.properties','.h','.c','.cpp','.cmake','.svg'}
EXACT = {'LICENSE','Dockerfile','Makefile','.gitignore','.gitattributes',
         'bun.lockb','openrouter-usage','AGENTS.md'}
SOURCES = {
 'opencode': HOME/'.config/opencode',
 'agent-learning': HOME/'Projects/agent-learning',
 'smart-router': HOME/'OpenCode/opencode-smart-router',
 'shellular': HOME/'OpenCode/shellular',
 'llm-server': HOME/'llm-server',
 'development': HOME/'Documents/Codex/evo-llm',
 'startup': HOME/'Projects/startup_scripts',
 'systemd': HOME/'.config/systemd/user',
}
OPENCODE_JSON = {'opencode.json','routing-policy.json','cloud-context.json','execution-adapters.json'}
RULES = [
 re.compile(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b'),
 re.compile(r'\bsk-(?:or-v1-)?[A-Za-z0-9_-]{20,}\b'),
 re.compile(r'\b\d{7,14}:[A-Za-z0-9_-]{30,}\b'),
]

def known_secrets():
    found=[]
    for p in [HOME/'llm-server/api.env',HOME/'llm-server/opencode.env',
              HOME/'llm-server/ha.env',HOME/'.config/opencode/telegram/bot.env']:
        if not p.exists(): continue
        for line in p.read_text().splitlines():
            if '=' not in line or line.lstrip().startswith('#'): continue
            key,value=line.split('=',1); value=value.strip().strip('"\'')
            if re.search(r'token|password|secret|api.?key',key,re.I) and len(value)>=8:
                found.append(value)
    return sorted(set(found),key=len,reverse=True)

def sanitize(data):
    try: text=data.decode('utf8')
    except UnicodeDecodeError: return data,False
    original=text
    for secret in known_secrets(): text=text.replace(secret,'[REDACTED CREDENTIAL]')
    for rule in RULES: text=rule.sub('[REDACTED CREDENTIAL]',text)
    return text.encode(),text!=original

def eligible(component,relative):
    name=relative.name
    if name.endswith(('.bak','.env','.log','.jsonl','.pyc')) or '.before' in name or '.bak.' in name:return False
    if name in {'service.json','tunnel.json','state.json','auth.json','ha-remote.json'}:return False
    if name.startswith('.env'):return False
    if component=='opencode' and len(relative.parts)==1:return name in OPENCODE_JSON or name=='AGENTS.md'
    if component in {'llm-server','development'}:
        return relative.suffix in {'.py','.mjs','.cjs','.js','.ts','.sh','.ps1'} or (component=='llm-server' and len(relative.parts)==1 and name=='servers.json')
    if component=='systemd':return relative.suffix in {'.service','.conf','.timer'}
    return relative.suffix in EXT or name in EXACT

def collect():
    expected={}; manifest=[]
    for component,source in SOURCES.items():
        if not source.exists():continue
        for directory,dirs,files in os.walk(source,followlinks=False):
            dirs[:]=sorted(d for d in dirs if d not in SKIP and not (Path(directory)/d).is_symlink())
            for name in sorted(files):
                path=Path(directory)/name; rel=path.relative_to(source)
                if path.is_symlink() or not eligible(component,rel):continue
                raw=path.read_bytes(); clean,redacted=sanitize(raw)
                dest=Path('components')/component/rel
                expected[str(dest)]=clean
                manifest.append({'source':str(path),'repository':str(dest),'sha256':hashlib.sha256(raw).hexdigest(),'executable':bool(path.stat().st_mode & 0o111),'redacted':redacted})
    cron=subprocess.run(['crontab','-l'],capture_output=True).stdout
    expected['components/systemd/user.crontab']=sanitize(cron)[0]
    instructions=HOME/'Documents/Codex/AGENTS.md'
    if instructions.exists():
        raw=instructions.read_bytes();dest='inventory/workspace-AGENTS.md'
        expected[dest]=sanitize(raw)[0]
        manifest.append({'source':str(instructions),'repository':dest,'sha256':hashlib.sha256(raw).hexdigest(),'executable':False,'redacted':False})
    def run(*args):return subprocess.check_output(args,text=True).strip()
    binary=HOME/'.opencode/bin/opencode'
    with binary.open('rb') as f:binary_hash=hashlib.file_digest(f,'sha256').hexdigest()
    upstream=ROOT/'upstream/opencode'
    source_repos=[HOME/'OpenCode'/p for p in ['shellular','shellular/packages','shellular/server','shellular/app','opencode-smart-router']]
    deployment={'opencode':{'version':run(str(binary),'--version'),'binary':str(binary),'sha256':binary_hash,
        'sourceTag':run('git','-C',str(upstream),'describe','--tags','--exact-match'),
        'sourceCommit':run('git','-C',str(upstream),'rev-parse','HEAD'),
        'sourceRelation':'Matching release version; build reproducibility not verified.'},
        'node':run(str(HOME/'.nvm/versions/node/v24.22.1/bin/node'),'--version'),
        'python':run('python3','--version'),
        'sourceRepositories':[{'path':str(p),'head':run('git','-C',str(p),'rev-parse','HEAD'),
          'trackedChanges':run('git','-C',str(p),'status','--porcelain','--untracked-files=no')} for p in source_repos]}
    expected['inventory/deployment.json']=(json.dumps(deployment,indent=2)+'\n').encode()
    expected['inventory/sources.json']=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
    return expected,manifest

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    expected,manifest=collect();changes=[]
    executable={m['repository']:m['executable'] for m in manifest}
    for name,data in expected.items():
        p=ROOT/name
        if not p.exists() or p.read_bytes()!=data or bool(p.stat().st_mode & 0o111)!=executable.get(name,False):
            changes.append(name)
            if not args.check:
                p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
                p.chmod(0o755 if executable.get(name,False) else 0o644)
    if (ROOT/'components').exists():
        for p in (ROOT/'components').rglob('*'):
            if p.is_file() and str(p.relative_to(ROOT)) not in expected:
                changes.append(str(p.relative_to(ROOT)))
                if not args.check:p.unlink()
    print(json.dumps({'mode':'check' if args.check else 'capture','sourceFiles':len(manifest),
                      'changed':len(changes),'redactedFiles':[x['repository'] for x in manifest if x['redacted']],
                      'changes':changes if args.check else []},indent=2))
    if args.check and changes:raise SystemExit(1)

if __name__=='__main__':main()
