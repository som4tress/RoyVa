#!/usr/bin/env python3
"""Transparent stdio-to-HTTP transport for the existing HA MCP server."""
import json,os,re,sys,urllib.request,urllib.error
from pathlib import Path
remote=json.loads((Path.home()/'llm-server/ha-remote.json').read_text())
headers={k:re.sub(r'\{env:([^}]+)\}',lambda m:os.environ[m[1]],v) for k,v in remote.get('headers',{}).items()}
headers.update({'Content-Type':'application/json','Accept':'application/json, text/event-stream'})
for line in sys.stdin:
 try:
  msg=json.loads(line)
  req=urllib.request.Request(remote['url'],data=json.dumps(msg).encode(),headers=headers,method='POST')
  with urllib.request.urlopen(req,timeout=30) as response:
   sid=response.headers.get('Mcp-Session-Id')
   if sid:headers['Mcp-Session-Id']=sid
   raw=response.read().decode();content_type=response.headers.get('Content-Type','')
  if msg.get('method')=='initialize':
   headers['MCP-Protocol-Version']=msg.get('params',{}).get('protocolVersion','2025-03-26')
  if not raw.strip():continue
  if 'text/event-stream' in content_type:
   for event in raw.replace('\r\n','\n').split('\n\n'):
    data='\n'.join(s[5:].strip() for s in event.splitlines() if s.startswith('data:'))
    if data:print(json.dumps(json.loads(data)),flush=True)
  else:print(json.dumps(json.loads(raw)),flush=True)
 except Exception as exc:
  if 'msg' in locals() and 'id' in msg:
   print(json.dumps({'jsonrpc':'2.0','id':msg['id'],'error':{'code':-32603,'message':'HA MCP transport failed: '+type(exc).__name__}}),flush=True)
