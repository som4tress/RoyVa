import {decodeResult,currentTurn} from './execution-templates.mjs';
const cell=x=>String(x??'').replace(/[\r\n|]/g,' ').slice(0,180);
export {isSimpleStatusQuery} from './user-scope.mjs';
import {isSimpleStatusQuery} from './user-scope.mjs';

export function formatNativeStatus(body,query){
 if(!isSimpleStatusQuery(query))return null;
 const turn=currentTurn(body,query);if(!turn)return null;
 const last=body.messages?.at(-1);if(last?.role!=='tool'||!last.tool_call_id)return null;
 const calls=turn.calls.filter(c=>c.id===last.tool_call_id);if(calls.length!==1||calls[0].function?.name!=='home-assistant_homeassistant__GetLiveContext')return null;
 if(turn.calls.some(c=>c.id!==last.tool_call_id&&!/GetLiveContext$|get_device_status$|get_device_status_report$/.test(c.function?.name||'')))return null;
 const data=decodeResult(last.content);if(typeof data?.result!=='string'||data.result.length>180000)return null;
 const raw=data.result.replace(/\\n/g,'\n');const blocks=raw.split(/(?:^|\n)\s*- names:\s*/).slice(1);if(!blocks.length||blocks.length>200)return null;
 const rows=[];for(const block of blocks){const name=block.split('\n')[0].trim(),domain=block.match(/\n\s*domain:\s*(\S+)/)?.[1],state=block.match(/\n\s*state:\s*([^\n]+)/)?.[1]?.trim().replace(/^['"]|['"]$/g,'');if(!name||!domain||!state)return null;
  if(!/\b(sensors?|entities|diagnostics?|trackers?|persons?|people)\b/i.test(query)&&!['light','switch','fan','climate','cover','lock','media_player','vacuum','humidifier','water_heater','alarm_control_panel'].includes(domain))continue;
  const b=block.match(/\n\s*brightness_pct:\s*['"]?(\d+)/)?.[1];rows.push([name,domain,state+(state==='on'&&b?' ('+b+'%)':'')]);}
 if(!rows.length)return null;
 let scope;try{const a=JSON.parse(calls[0].function.arguments||'{}');scope=Object.entries(a).map(([k,v])=>k+': '+(Array.isArray(v)?v.join(', '):v)).join('; ')||'exposed HA entities';}catch{return null;}
 return 'Live status — '+cell(scope)+'\n\n| Device | Type | State |\n|---|---|---|\n'+rows.map(r=>'| '+r.map(cell).join(' | ')+' |').join('\n');
}
