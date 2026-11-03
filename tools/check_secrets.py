#!/usr/bin/env python3
"""Reject credential formats and known local secrets in the staged tree."""
import subprocess,sys
from pathlib import Path
from capture import ROOT,RULES,known_secrets

files=subprocess.check_output(['git','diff','--cached','--name-only','--diff-filter=ACMR','-z'],cwd=ROOT).decode().split('\0')
bad=[]
for name in filter(None,files):
    path=Path(name)
    if name.startswith('upstream/'):continue
    if path.name.endswith('.env') or path.name in {'service.json','tunnel.json','auth.json','state.json'}:
        bad.append(name);continue
    data=subprocess.check_output(['git','show',':'+name],cwd=ROOT)
    text=data.decode('utf8',errors='ignore')
    if any(secret in text for secret in known_secrets()) or any(rule.search(text) for rule in RULES):bad.append(name)
if bad:
    print('Credential scan failed for paths only:',*sorted(set(bad)),sep='\n');sys.exit(1)
print('Staged credential scan passed.')
