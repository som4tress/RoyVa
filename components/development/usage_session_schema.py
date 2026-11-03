import sqlite3,json,pathlib
c=sqlite3.connect('file:'+str(pathlib.Path.home()/'.local/share/opencode/opencode.db')+'?mode=ro',uri=True)
names=[r[0] for r in c.execute("select name from sqlite_master where type='table'") if 'session' in r[0]];print(names)
for n in names:
 if n in ['session_message','session_message_part','session_event']:continue
 cols=[r[1] for r in c.execute('pragma table_info('+n+')')]
 print(n,cols)
 if 'data' in cols:
  row=c.execute('select data from '+n+' order by rowid desc limit 1').fetchone()
  if row:
   try:print('keys',list(json.loads(row[0])))
   except:pass
