import sqlite3,pathlib,json
c=sqlite3.connect('file:'+str(pathlib.Path.home()/'.local/share/opencode/opencode.db')+'?mode=ro',uri=True)
print('part types',c.execute('select distinct type from session_part').fetchall())
for row in c.execute("select data from session_message where type='assistant' and data like '%subagent%' order by time_created desc limit 1"):
 d=json.loads(row[0]);print('assistant keys',list(d));print('content types',[(p.get('type'),list(p)) for p in d.get('content',[])][:3])
