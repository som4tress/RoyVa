from pathlib import Path
h=Path.home();base=h/'.config/opencode'
p=base/'plugins/ha-mcp-routing/index.js';s=p.read_text();needle="   const seeded=isHAFollowup(text)?"
assert needle in s;s=s.replace(needle,"""   if(isLocationExplanation(text)){
    turns.delete(event.sessionID);await ctx.storage?.remove(key(event.sessionID));
    if(prior?.previous)await ctx.session.switchModel({sessionID:event.sessionID,model:prior.previous});
    return;
   }
   const seeded=isHAFollowup(text)?""")
p.write_text(s)
p=base/'mcp/ha_template_runner.py';s=p.read_text().replace("password|bearer|api.?key|secret|\\btoken\\b|[;`{}]", "password|bearer|api.?key|secret|\\btoken\\b|\\b(route|deepseek|glm|qwen|model)\\b|[;`{}]")
s=s.replace("  if not standalone(q) or set(args)-{'person','date'}", "  safe_query=re.sub(r'\\b(?:last|past)\\s+(?:(?:\\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\\s+)?hours?\\b','rolling window',q,flags=re.I) if args.get('hours') is not None else q\n  if not standalone(safe_query) or set(args)-{'person','date','hours'}")
s=s.replace("  result={'person':args['person']};today=", """  result={'person':args['person']}
  if args.get('hours') is not None:
   hours=args['hours'];numbers={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12}
   match=re.search(r'\\b(?:last|past)\\s+(?:(\\d+|'+ '|'.join(numbers)+r')\\s+)?hours?\\b',q,re.I)
   if not match or type(hours) is not int or not 1<=hours<=168 or args.get('date'):raise ValueError('Rolling hour scope is not explicit.')
   value=(match[1] or 'one').lower();requested=int(value) if value.isdigit() else numbers[value]
   if requested!=hours:raise ValueError('Rolling hour scope mismatch.')
   return {'person':args['person'],'hours':hours}
  today=""")
s=s.replace("  expected=args.get('date') or dt.datetime.now(TZ).date().isoformat()", """  expected=args.get('date') or dt.datetime.now(TZ).date().isoformat()
  if args.get('hours') is not None and data.get('requested_range',{}).get('hours')!=args['hours']:raise ValueError('History time window mismatch.')""")
p.write_text(s)
p=base/'lib/execution-templates.mjs';s=p.read_text()
s=s.replace("  const title=cell(data.person)+' — recorded locations on '+cell(data.date)+' (America/Los_Angeles)';", "  const range=data.requested_range;\n  const title=range?.hours?cell(data.person)+' — recorded history, last '+range.hours+' hour(s) (America/Los_Angeles)':cell(data.person)+' — recorded locations on '+cell(data.date)+' (America/Los_Angeles)';")
s=s.replace("if(/\\b(timeline|when|times?|intervals?|detailed|chronological)\\b/i.test(query)){", "if(range?.hours||/\\b(timeline|when|times?|intervals?|detailed|chronological)\\b/i.test(query)){")
s=s.replace("return title+'\\n\\n| Recorded location | From (PT) | To (PT) |\\n|---|---|---|\\n'+data.recorded_locations.map(r=>", "const timeline=[...data.recorded_locations,...(data.transit_or_unknown_intervals||[]).map(r=>({...r,location:r.status}))].sort((a,b)=>a.from.localeCompare(b.from));\n   return title+'\\n\\n| Recorded location | From (PT) | To (PT) |\\n|---|---|---|\\n'+timeline.map(r=>")
p.write_text(s)
p=base/'instructions/ha-compact.md';p.write_text(p.read_text()+'\nFor rolling history such as the last N hours, call get_visited_locations with hours=N and no date. Report chronological zone/transit intervals for that requested window, not the current person state. Questions explaining an incorrect prior reply are meta questions; do not substitute a fresh current-location lookup.\n')
p=base/'instructions/routing.md';p.write_text(p.read_text()+'\nHistory/current-location correction: the deterministic Maps lookup is only for clear current-location requests. Historical/time-window queries and explanatory corrections must never take that shortcut. get_visited_locations supports rolling hours (1..168) mutually exclusive with date. Explicit route/use DeepSeek requests bypass deterministic current-location lookup and local HA selection.\n')
print('Rolling-hour history bound to its requested window; explanations bypass learned HA routes; explicit model choices excluded from template replay.')
