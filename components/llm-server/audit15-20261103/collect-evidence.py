import sqlite3,json,re,os
from pathlib import Path
root=Path('/home/somdutta/llm-server/audit15-20261103');results=json.loads((root/'results.json').read_text());db=sqlite3.connect('file:/home/somdutta/.local/share/opencode/opencode.db?mode=ro',uri=True)
pattern=re.compile(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b|\bsk-(?:or-v1-)?[A-Za-z0-9_-]{20,}\b')
secrets=[]
for envname in ['api.env','opencode.env','ha.env']:
 for line in (Path('/home/somdutta/llm-server')/envname).read_text().splitlines():
  if '=' not in line:continue
  key,value=line.split('=',1);value=value.strip('"\'')
  if re.search(r'(TOKEN|KEY|PASSWORD|SECRET)$',key) and len(value)>=8:secrets.extend([value,json.dumps(value)[1:-1]])
def redact(s):
 s=pattern.sub('[REDACTED CREDENTIAL]',s)
 for value in secrets:s=s.replace(value,'[REDACTED CREDENTIAL]')
 return s
audit=[]
for r in results:
 row={'id':r['id'],'session':r['sessionId'],'tools':[],'credentialInToolOutput':False,'models':[],'errors':[]}
 for mid,raw in db.execute("select id,data from session_message where session_id=? and type='assistant' and time_created>=? and time_created<=? order by time_created",(r['sessionId'],r['startedAt'],int(r['startedAt']+r['seconds']*1000))):
  d=json.loads(raw);row['models'].append({'id':mid,'model':d.get('model'),'tokens':d.get('tokens'),'cost':d.get('cost')})
  if d.get('error'):row['errors'].append(json.loads(redact(json.dumps(d['error']))))
  for p in d.get('content',[]):
   if p.get('type')!='tool':continue
   state=p.get('state',{});content=state.get('content',[]);wire=json.dumps(content)
   secret=bool(pattern.search(wire)) or any(v in wire for v in secrets);row['credentialInToolOutput']|=secret
   row['tools'].append({'assistant':mid,'name':p.get('name'),'status':state.get('status'),'time':p.get('time'),'input':json.loads(redact(json.dumps(state.get('input',{})))),'content':json.loads(redact(wire)),'credentialInOutput':secret})
 audit.append(row)
p=root/'tool-evidence.json';p.write_text(json.dumps(audit,indent=2));p.chmod(0o600)
print(json.dumps([{'id':r['id'],'tools':len(r['tools']),'credentialInOutput':r['credentialInToolOutput'],'errors':len(r['errors'])} for r in audit]))
