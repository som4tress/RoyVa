import sqlite3,json,pathlib
c=sqlite3.connect('file:'+str(pathlib.Path.home()/'.local/share/opencode/opencode.db')+'?mode=ro',uri=True)
for row in c.execute("select data from session_part where type='tool' and data like '%subagent%' order by time_created desc limit 2"):
 d=json.loads(row[0]);print('part keys',list(d));print('name',d.get('tool'),d.get('name'));s=d.get('state',{});print('state keys',list(s));print('metadata keys',list(s.get('metadata',{})))
