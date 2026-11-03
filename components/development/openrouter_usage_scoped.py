#!/usr/bin/env python3
"""Stateless usage for an explicit session/turn. Never consumes a shared mark."""
import argparse,json,os,re,sqlite3,sys,urllib.request
from pathlib import Path
DEFAULT_DB=Path.home()/'.local/share/opencode/opencode.db'

def collect(db,session,ids=None,since_ms=None,until_ms=None):
 con=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True);con.row_factory=sqlite3.Row
 if ids:
  rows=list(con.execute("select id,data,time_created from session_message where session_id=? and type='assistant' and id in ("+','.join('?' for _ in ids)+')',[session,*ids]))
 else:
  rows=list(con.execute("select id,data,time_created from session_message where session_id=? and type='assistant' and time_created>=? and time_created<=?",[session,since_ms,until_ms or 9223372036854775807]))
 root_ids=[r['id'] for r in rows];seen=set(root_ids);allrows=list(rows);queue=[]
 def references(value):
  found=[]
  if isinstance(value,dict):
   for key,v in value.items():
    if key in ['sessionID','sessionId','session_id'] and isinstance(v,str):found.append(v)
    elif isinstance(v,(dict,list)):found.extend(references(v))
  elif isinstance(value,list):
   for v in value:found.extend(references(v))
  return found
 def children(parent,message_ids):
  if not message_ids:return []
  found=[]
  try:
   parts=con.execute("select data from session_part where session_id=? and type='tool' and message_id in ("+','.join('?' for _ in message_ids)+')',[parent,*message_ids])
   for part in parts:
    obj=json.loads(part[0]);name=obj.get('tool') or obj.get('name')
    if name!='subagent':continue
    for child in references(obj.get('state',{}).get('metadata',{})):
     if con.execute('select 1 from session_v2 where id=? and parent_id=?',[child,parent]).fetchone():found.append(child)
  except sqlite3.OperationalError:pass
  return found
 queue.extend(children(session,root_ids));visited=set()
 lower=since_ms if since_ms is not None else min((r['time_created'] for r in rows),default=0)
 while queue:
  child=queue.pop()
  if child in visited:continue
  visited.add(child)
  childrows=list(con.execute("select id,data,time_created from session_message where session_id=? and type='assistant' and time_created>=? and time_created<=?",[child,lower,until_ms or 9223372036854775807]))
  queue.extend(children(child,[r['id'] for r in childrows]))
  for row in childrows:
   if row['id'] not in seen:seen.add(row['id']);allrows.append(row)
 totals=dict(cost=0.0,fresh=0,cached=0,output=0,reasoning=0,requests=0)
 for row in allrows:
  d=json.loads(row['data']);tokens=d.get('tokens') or {};provider=(d.get('model') or {}).get('providerID')
  if provider!='openrouter' or not tokens:continue
  if not any(tokens.get(k) for k in ['input','output','reasoning']) and not (tokens.get('cache') or {}).get('read'):continue
  totals['requests']+=1;totals['cost']+=float(d.get('cost') or 0)
  totals['fresh']+=int(tokens.get('input') or 0);totals['cached']+=int((tokens.get('cache') or {}).get('read') or 0)
  totals['output']+=int(tokens.get('output') or 0);totals['reasoning']+=int(tokens.get('reasoning') or 0)
 totals['cost']=round(totals['cost'],8);con.close();return totals

def format_usage(t):
 if not t['requests']:return ''
 fmt=lambda n:f'{n/1000:.1f}k' if n>=1000 else str(n)
 line=f"Usage: ${t['cost']:.4f} · in {fmt(t['fresh'])} fresh / {fmt(t['cached'])} cached · out {fmt(t['output'])}"
 if t['reasoning']:line+=f" · think {fmt(t['reasoning'])}"
 return line

def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--session',required=True);scope=p.add_mutually_exclusive_group(required=True)
 scope.add_argument('--message-ids',help='Comma-separated assistant IDs from this completed invocation');scope.add_argument('--since-ms',type=int)
 p.add_argument('--until-ms',type=int);p.add_argument('--json',action='store_true');p.add_argument('--db',default=str(DEFAULT_DB))
 a=p.parse_args(argv);ids=[x for x in (a.message_ids or '').split(',') if x]
 t=collect(a.db,a.session,ids or None,a.since_ms,a.until_ms)
 print(json.dumps(t) if a.json else format_usage(t))
if __name__=='__main__':main()
