import json,subprocess,os,time,sqlite3
root='/home/somdutta/llm-server/context-hygiene-20261103'
cfg=json.load(open('/home/somdutta/.config/opencode/service.json'));env=os.environ.copy();env['OPENCODE_PASSWORD']=cfg['password']
sid='ses_tg_6064019420_mvxqey2l'
def api(method,path,data=None):
 cmd=['/home/somdutta/.opencode/bin/opencode','api','--server','http://127.0.0.1:49374',method,path]
 if data is not None:cmd+=['--data',json.dumps(data)]
 r=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=20)
 if r.returncode:raise RuntimeError(r.stderr[:200])
 j=json.loads(r.stdout);return j.get('data',j)
results=[]
for prompt in ['Use the shell tool to read MemAvailable and SwapFree from /proc/meminfo. Return only those two values in GiB.','Which of those two values was larger? Use the values just measured; do not call tools.']:
 started=int(time.time()*1000);ack=api('post','/api/session/'+sid+'/prompt',{'text':prompt});print('Accepted diagnostic prompt',flush=True)
 for _ in range(100):
  time.sleep(2);session=api('get','/api/session/'+sid)
  if session.get('time',{}).get('idle',0)>=started:break
 else:raise RuntimeError('diagnostic did not finish within 200 seconds')
 c=sqlite3.connect('/home/somdutta/.local/share/opencode/opencode.db');rows=c.execute("SELECT id,data FROM session_message WHERE session_id=? AND type='assistant' AND time_created>=? ORDER BY time_created",(sid,started)).fetchall();c.close()
 turns=[]
 for mid,raw in rows:
  d=json.loads(raw);turns.append({'id':mid,'model':d.get('model'),'tokens':d.get('tokens'),'cost':d.get('cost'),'tools':[p.get('name') for p in d.get('content',[]) if p.get('type')=='tool'],'text':'\n'.join(p.get('text','') for p in d.get('content',[]) if p.get('type')=='text')})
 result={'prompt':prompt,'elapsedMs':int(time.time()*1000)-started,'turns':turns};results.append(result);print(json.dumps(result),flush=True)
 open(root+'/live-result.json','w').write(json.dumps(results,indent=2))
