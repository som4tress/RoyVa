from pathlib import Path
h=Path.home();p=h/'.config/opencode/mcp/ha_template_runner.py';s=p.read_text()
s=s.replace(" if re.search(r'\\b(it|them", " if re.search(r'password|bearer|api.?key|secret|\\btoken\\b|[;`{}]',s):return False\n if re.search(r'\\b(?:and|then|also)\\s+(?:then\\s+)?(?:turn|switch|set|run|show|share|check|send|announce|broadcast|play|summarize)\\b',s):return False\n if re.search(r'\\b(it|them")
s=s.replace('tomorrow|schedule|never|not', 'tomorrow|tonight|later|minutes?|seconds?|hours?|schedule|except|never|not')
s=s.replace(" if tool==STATUS and not grounded(q,args.get('name','')):", " if tool==STATUS and re.search(r'\\b(brightness|bright|temperature|degrees|percentage|speed|battery|power|watt|who|how|when|since)\\b',q,re.I):raise ValueError('Status request needs interpretation beyond the saved formatter.')\n  if tool==STATUS and not grounded(q,args.get('name','')):")
s=s.replace("  if not standalone(q) or set(args)-{'person','date'}", "  if re.search(r'how long|how many|duration|distance|miles|kilomet|total|\\bstops?\\b|stopped',q,re.I):raise ValueError('History request requires additional analysis.')\n  if not standalone(q) or set(args)-{'person','date'}")
p.write_text(s)
p=h/'.config/opencode/lib/execution-templates.mjs';s=p.read_text().replace("'mcp/ha_mcp_transport.py'];", "'mcp/ha_mcp_transport.py','instructions/home-assistant.md','instructions/ha-compact.md'];")
s=s.replace(" return {query:content,tail,calls,results};", " const priorConstraints=msgs.slice(0,index).filter(m=>m.role==='user').some(m=>/do not|don't|never|unless|forbid|permission|class|sleeping/i.test(typeof m.content==='string'?m.content:JSON.stringify(m.content)));\n return {query:content,tail,calls,results,priorConstraints};")
s=s.replace(" if(!call||!SUPPORTED.has(call.function?.name))return null;", " if(!call||!SUPPORTED.has(call.function?.name))return null;\n if(turn.priorConstraints&&/HassTurn(?:On|Off)$/.test(call.function.name))return null;")
s=s.replace('export function formatProcedure(tool,data){', "export function formatProcedure(tool,data,query=''){")
s=s.replace("  const names=[...new Set(data.recorded_locations.map(x=>x.location))];", """  if(/\\b(timeline|when|times?|intervals?|detailed|chronological)\\b/i.test(query)){
   const time=x=>{try{return new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(x))}catch{return 'unknown'}};
   return title+'\\n\\n| Recorded location | From (PT) | To (PT) |\\n|---|---|---|\\n'+data.recorded_locations.map(r=>'| '+[r.location,time(r.from),r.ongoing?'ongoing':time(r.to)].map(cell).join(' | ')+' |').join('\\n')+'\\n\\nRecorded zones may include brief crossings.';
  }
  const names=[...new Set(data.recorded_locations.map(x=>x.location))];""")
s=s.replace(" const started=Date.now(),result=await run", " if(template.recipe.kind==='write'&&turn.priorConstraints)return null;\n const started=Date.now(),result=await run")
s=s.replace('formatProcedure(template.recipe.tool,result.data)', 'formatProcedure(template.recipe.tool,result.data,turn.query)').replace('formatProcedure(candidate.tool,data)', 'formatProcedure(candidate.tool,data,candidate.query)')
p.write_text(s)
