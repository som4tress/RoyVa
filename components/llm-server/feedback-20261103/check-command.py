import json,os,subprocess,sqlite3,pathlib
h=pathlib.Path.home();env=dict(os.environ,OPENCODE_PASSWORD=json.loads((h/'.config/opencode/service.json').read_text())['password'])
sid=json.loads((h/'llm-server/concise-output-20261103/result.json').read_text())['sessionId']
def api(method,path,data=None):
 args=[str(h/'.opencode/bin/opencode'),'api','--server','http://127.0.0.1:49374',method,path]
 if data is not None:args+=['--data',json.dumps(data)]
 r=subprocess.run(args,env=env,capture_output=True,text=True,timeout=20)
 if r.returncode:raise RuntimeError(r.stderr[:500])
 return json.loads(r.stdout) if r.stdout.strip() else None
c=sqlite3.connect('file:'+str(h/'.local/share/opencode/opencode.db')+'?mode=ro',uri=True)
count=lambda:c.execute("select count(*) from session_message where session_id=? and type='assistant'",(sid,)).fetchone()[0]
before=count()
for text in ['accept','status','reject Diagnostic feedback test; no tool should be created']:
 api('post',f'/api/session/{sid}/command',{'name':'feedback','text':text})
rows=api('get',f'/api/session/{sid}/message')['data'];shells=[r for r in rows if r['type']=='shell']
assert count()==before,'Feedback unexpectedly invoked a model'
print(json.dumps({'command_calls':3,'new_assistant_messages':count()-before,'shell_acknowledgements':len(shells),'last_shell':shells[0] if shells else None})[:2000])
(h/'llm-server/feedback-20261103/native-result.json').write_text(json.dumps({'sessionId':sid,'new_assistant_messages':count()-before,'shells':shells},indent=2))
