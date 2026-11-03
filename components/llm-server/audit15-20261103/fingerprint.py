from pathlib import Path
import hashlib,json
root=Path('/home/somdutta/.config/opencode');paths=[]
for folder in ['lib','plugins','instructions','telegram','mcp']:
 paths += [p for p in (root/folder).rglob('*') if p.is_file() and p.suffix in ['.mjs','.js','.ts','.py','.md'] and 'node_modules' not in p.parts and '__pycache__' not in p.parts]
paths += [root/'opencode.json',root/'routing-policy.json',root/'cloud-context.json',root/'scripts/openrouter-usage',Path('/home/somdutta/llm-server/servers.json')]
print(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths)) if p.exists()},indent=2))
