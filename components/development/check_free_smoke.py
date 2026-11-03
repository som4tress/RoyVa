import sqlite3,json,pathlib
c=sqlite3.connect('file:'+str(pathlib.Path.home()/'.local/share/opencode/opencode.db')+'?mode=ro',uri=True)
sid=c.execute("select session_id from session_message where session_id like 'ses_review_free_%' order by time_created desc limit 1").fetchone()[0]
rows=list(c.execute('select type,data from session_message where session_id=? order by time_created',[sid]))
print('Free smoke event types:',[r[0] for r in rows])
print('Quota error recorded:',any('free usage limit' in raw.lower() or 'quota' in raw.lower() for _,raw in rows))
for typ,raw in rows:
 d=json.loads(raw)
 if typ=='assistant':print('Actual replying provider:',(d.get('model') or {}).get('providerID'))
