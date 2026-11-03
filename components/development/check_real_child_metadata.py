import sqlite3,json,pathlib
c=sqlite3.connect('file:'+str(pathlib.Path.home()/'.local/share/opencode/opencode.db')+'?mode=ro',uri=True)
for row in c.execute("select data from session_message where type='assistant' and data like '%subagent%' order by time_created desc limit 5"):
 d=json.loads(row[0])
 for p in d.get('content',[]):
  if p.get('name')=='subagent':print('tool state keys',list(p.get('state',{})));print('metadata',p.get('state',{}).get('metadata',{}));print('time',p.get('time'));raise SystemExit
