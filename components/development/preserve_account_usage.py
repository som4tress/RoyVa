from pathlib import Path
p=Path.home()/'.config/opencode/scripts/openrouter-usage';s=p.read_text()
s=s.replace('def main(argv=None):', '''def account_usage(db):
 key=os.environ.get('OPENROUTER_API_KEY')
 if not key:
  try:
   con=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
   for (value,) in con.execute('select value from credential'):
    match=re.search(r'sk-or-v1-[A-Za-z0-9]+',str(value))
    if match:key=match.group(0);break
   con.close()
  except sqlite3.Error:pass
 if not key:raise ValueError('OpenRouter account credentials unavailable.')
 req=urllib.request.Request('https://openrouter.ai/api/v1/credits',headers={'Authorization':'Bearer '+key})
 try:
  data=json.load(urllib.request.urlopen(req,timeout=4))['data']
  return {'total':float(data['total_credits']),'used':float(data['total_usage'])}
 except Exception:raise ValueError('OpenRouter account usage unavailable.')

def main(argv=None):''')
s=s.replace("p.add_argument('--session',required=True);scope=p.add_mutually_exclusive_group(required=True)","p.add_argument('--session');scope=p.add_mutually_exclusive_group()")
s=s.replace("p.add_argument('--until-ms',type=int);", "p.add_argument('--account',action='store_true',help='Separate account-wide credit snapshot; never treated as this turn cost');p.add_argument('--peek',action='store_true',help=argparse.SUPPRESS);p.add_argument('--until-ms',type=int);")
s=s.replace(" t=collect(a.db,a.session,ids or None,a.since_ms,a.until_ms)\n print(json.dumps(t) if a.json else format_usage(t))", """ if not a.session:
  if not a.account:p.error('Specify --session with a turn scope, or --account for a separate credit snapshot.')
  try:acct=account_usage(a.db)
  except ValueError as e:p.exit(1,str(e)+'\\n')
  print(json.dumps({'account':acct}) if a.json else f\"Account: ${acct['used']:.2f}/${acct['total']:.2f} used · ${acct['total']-acct['used']:.2f} remaining\");return
 if not ids and a.since_ms is None:p.error('--session requires --message-ids or --since-ms.')
 t=collect(a.db,a.session,ids or None,a.since_ms,a.until_ms)
 if a.account:
  try:t['account']=account_usage(a.db)
  except ValueError:t['account']=None
 print(json.dumps(t) if a.json else format_usage(t))""")
p.write_text(s)
p=Path.home()/'.config/opencode/instructions/usage-footer.md';p.write_text(p.read_text()+'\nFor an explicitly requested account balance, run scripts/openrouter-usage --account. This is separate account-wide usage, never the per-turn cost.\n')
p=Path('/tmp/test_bridge_review_live.mjs');s=p.read_text();s=s.replace("process.env.OPENCODE_TG_MODEL=JSON.parse(readFileSync(home+'/.config/opencode/opencode.json','utf8')).model;", "const configuredDefault=JSON.parse(readFileSync(home+'/.config/opencode/opencode.json','utf8')).model;delete process.env.OPENCODE_TG_MODEL;")
s=s.replace("process.env.OPENCODE_TG_MODEL],['paid','Reply exactly: usage check.','openrouter/deepseek/deepseek-v4.1-flash-1017'],", "undefined],")
p.write_text(s)
