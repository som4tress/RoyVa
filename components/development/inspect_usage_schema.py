import sqlite3,json,pathlib
c=sqlite3.connect('file:'+str(pathlib.Path.home()/'.local/share/opencode/opencode.db')+'?mode=ro',uri=True)
for table in ['session','session_message']:
 print(table,[r[1] for r in c.execute('pragma table_info('+table+')')])
 try:
  row=c.execute('select data from '+table+' order by rowid desc limit 1').fetchone();d=json.loads(row[0]);print('json keys',list(d))
 except Exception as e:print(type(e).__name__)
