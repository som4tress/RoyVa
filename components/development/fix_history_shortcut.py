from pathlib import Path
h=Path.home();base=h/'.config/opencode';backup=h/'opencode-migration-backup/history-shortcut-fix';backup.mkdir(exist_ok=True)
for name in ['lib/media-deadline-proxy.mjs','plugins/ha-mcp-routing/index.js','mcp/ha_history.py']:
 p=base/name;(backup/name.replace('/','__')).write_text(p.read_text())
p=base/'lib/media-deadline-proxy.mjs';s=p.read_text();s="import {isCurrentLocationQuery} from './location-query.mjs';\n"+s
s=s.replace("  if(!/(\\bwhere|\\blocation\\b|\\bcoordinates?\\b|\\bwhere's\\b)/.test(q))return null;", "  if(!isCurrentLocationQuery(query,PEOPLE))return null;")
s=s.replace("reportWire(incoming,kind==='primary'?direct.text+ZERO_FOOTER:direct.text)","reportWire(incoming,kind==='primary'&&direct.zeroLLM?direct.text+ZERO_FOOTER:direct.text)")
s=s.replace("reportWire(incoming,kind==='primary'?report+ZERO_FOOTER:report)","reportWire(incoming,report)");p.write_text(s)
p=base/'plugins/ha-mcp-routing/index.js';s=p.read_text();s="import {isLocationExplanation} from '../../lib/location-query.mjs';\n"+s
s=s.replace("const s=text.toLowerCase();if(coding(s)||routingMeta(s)||isMixedRequest(s))return null;","const s=text.toLowerCase();if(coding(s)||routingMeta(s)||isLocationExplanation(s)||isMixedRequest(s))return null;")
needle="   const prior=await stateFor(event.sessionID);"
s=s.replace(needle,needle+'''
   if(/\\b(?:route|switch|use)\\s+(?:to\\s+)?deepseek\\b/i.test(text)){
    await save(event.sessionID,{kind:'fallback',reason:'The user explicitly requested DeepSeek',previous:CLOUD,startedAt:Date.now(),calls:0,failures:0,requestText:text});
    await ctx.session.switchModel({sessionID:event.sessionID,model:CLOUD});return;
   }''')
s=s.replace('Local Qwen failed this turn: ', 'HA routing status: ')
s=s.replace("You are now the DeepSeek fallback.","You are now handling this request on DeepSeek.");p.write_text(s)
p=base/'mcp/ha_history.py';s=p.read_text()
s=s.replace("'required':['person'],'additionalProperties':False", "'required':['person'],'additionalProperties':False")
s=s.replace("'date':{'type':'string','description':'Local date YYYY-MM-DD; omit for today in America/Los_Angeles.'}","'date':{'type':'string','description':'Local date YYYY-MM-DD; omit for today. Mutually exclusive with hours.'},'hours':{'type':'integer','minimum':1,'maximum':168,'description':'Rolling last N hours, e.g. 1 for the last hour. Mutually exclusive with date.'}")
old=" start=dt.datetime.combine(day,dt.time(),TZ); end=min(start+dt.timedelta(days=1),now)"
new=""" hours=args.get('hours')
 if hours is not None:
  if type(hours) is not int or not 1<=hours<=168 or args.get('date'):raise ValueError('hours must be 1..168 and cannot be combined with date.')
  start=(now.astimezone(dt.timezone.utc)-dt.timedelta(hours=hours)).astimezone(TZ);end=now
 else:start=dt.datetime.combine(day,dt.time(),TZ);end=min(start+dt.timedelta(days=1),now)"""
assert old in s;s=s.replace(old,new)
s=s.replace("'timezone':str(TZ),'source':'Home Assistant recorder:","'timezone':str(TZ),'requested_range':{'from':start.isoformat(timespec='seconds'),'to':end.isoformat(timespec='seconds'),'hours':hours},'source':'Home Assistant recorder:")
p.write_text(s)
print('Current-location fast path narrowed; history supports rolling hours; explicit DeepSeek requests are honored; false zero-token labels removed.')
