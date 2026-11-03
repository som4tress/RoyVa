from pathlib import Path
h=Path.home();p=h/'.config/opencode/mcp/ha_template_runner.py';s=p.read_text()
s=s.replace(" return not re.search(r'\\b(turn|toggle|enable|disable|activate|delete|remove|run|execute|why|explain|compare|cause|caused)\\b',s)", " return not re.search(r'\\b(turn|toggle|enable|disable|activate|delete|remove|run|execute|why|explain|compare|cause|caused|not|except)\\b',s)")
s=s.replace("  if tool==STATUS and re.search", """  if tool==STATUS and re.search(r'\\b(and|also|both|plus)\\b|[,;&]',q,re.I):raise ValueError('Multi-target status requires the agent or a report.')
  if tool==REPORT:
   if args.get('name') and not grounded(q,args['name']):raise ValueError('Report name filter is not grounded.')
   if not args.get('name') and not re.search(r'\\b(all|every|devices|entities|home|house)\\b',q,re.I):raise ValueError('Unfiltered report is not explicitly requested.')
   if args.get('state') and not re.search(r'\\b'+re.escape(str(args['state']))+r'\\b',q,re.I):raise ValueError('Report state filter is not requested.')
   if args.get('include_diagnostics') and not re.search(r'\\b(sensors?|diagnostics?|entities|trackers?|people|person)\\b',q,re.I):raise ValueError('Diagnostic scope is not requested.')
   if not re.search(r'\\b(devices|entities|everything)\\b',q,re.I) and re.search(r'\\blights?\\b',q,re.I) and not args.get('name'):
    if not args.get('domains') or any(d not in ['light','switch'] for d in args['domains']):raise ValueError('Light-only report scope is too broad.')
  if tool==STATUS and re.search""")
s=s.replace("  if not standalone(q) or set(args)-{'person','date'}", """  named=[p for p in PEOPLE.values() if re.search(r'\\b'+re.escape(p)+r'\\b',q,re.I)]
  if len(named)!=1 or (re.search(r'\\btoday\\b',q,re.I) and re.search(r'\\byesterday\\b',q,re.I)) or len(re.findall(r'\\b\\d{4}-\\d{2}-\\d{2}\\b',q))>1:raise ValueError('History needs exactly one explicit person and day.')
  if not standalone(q) or set(args)-{'person','date'}""")
p.write_text(s)
p=h/'.config/opencode/lib/execution-templates.mjs';s=p.read_text()
s=s.replace('function audit(event){try{mkdirSync(dirname(STORE)', 'function audit(event,path=STORE){try{mkdirSync(dirname(path)')
s=s.replace("appendFileSync(dirname(STORE)+'/execution.jsonl'", "appendFileSync(dirname(path)+'/execution.jsonl'")
s=s.replace("ms:Date.now()-started});return result.write_uncertain", "ms:Date.now()-started},path);return result.write_uncertain")
s=s.replace("ms:Date.now()-started});\n return {text,source:'verified-template'", "ms:Date.now()-started},path);\n return {text,source:'verified-template'")
s=s.replace("kind:proof.recipe.kind,saved});", "kind:proof.recipe.kind,saved},path);")
s=s.replace(" if(turn.priorConstraints&&/HassTurn", " if(['ha-history_get_device_status','ha-history_get_visited_locations'].includes(call.function.name)&&turn.calls.length!==1)return null;\n if(turn.priorConstraints&&/HassTurn")
p.write_text(s)
