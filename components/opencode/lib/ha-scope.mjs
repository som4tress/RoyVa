import {readFileSync} from 'node:fs';
import {spawn}from'node:child_process';import{homedir}from'node:os';import{isSimpleStatusQuery}from'./ha-native-status.mjs';
let metadata=null,at=0,pending=null;
const norm=s=>String(s).toLowerCase().replace(/[^\p{L}\p{N}]+/gu,' ').trim();
export function chooseReportScope(query,args,registry){
 if(!isSimpleStatusQuery(query))return args;
 if(/\b(thermostat|dimmer|lamp|fan|speaker|switch|sensor|lock|cover|vacuum)\b/i.test(query)&&!/\b(all|every|devices|entities|lights|switches|fans|speakers|thermostats|sensors)\b/i.test(query))return args;
 const q=' '+norm(query)+' ';
 const hits=(rows,kind)=>rows.flatMap(r=>[r.name,...(r.aliases||[])].filter(Boolean).filter(v=>q.includes(' '+norm(v)+' ')).map(v=>({kind,name:r.name,label:norm(v)})));
 const candidates=[...hits(registry.floors||[],'floor'),...hits(registry.areas||[],'area')];
 if(!candidates.length)return args;
 const longest=Math.max(...candidates.map(v=>v.label.length));let matches=candidates.filter(v=>v.label.length===longest);
 matches=[...new Map(matches.map(v=>[v.kind+':'+v.name,v])).values()];
 if(matches.length>1){const area=/\b(area|room)\b/i.test(query),floor=/\b(floor|storey|story)\b/i.test(query);if(area!==floor)matches=matches.filter(v=>v.kind===(area?'area':'floor'));}
 if(matches.length!==1)throw new Error('Area and floor display names are ambiguous. Specify area/floor or use distinct configured names.');
 const selected=matches[0],scope={[selected.kind]:selected.name};
 const floors=(registry.floors||[]).filter(r=>r.name===selected.name),areas=(registry.areas||[]).filter(r=>r.name===selected.name);
 if(!scope)return args;
 const out={...args,...scope};if(scope.floor)delete out.area;else delete out.floor;
 if(out.name&&[...floors,...areas].some(r=>norm(r.name)===norm(out.name)||norm(r.area_id||r.floor_id||'')===norm(out.name)))delete out.name;
 return out;
}
async function catalog(){
 if(metadata&&Date.now()-at<60000)return metadata;if(pending)return pending;
 pending=new Promise(resolve=>{const code='import sys,json;sys.path.insert(0,'+JSON.stringify(homedir()+'/.config/opencode/mcp')+');import ha_registry;s=ha_registry.snapshot();print(json.dumps({"areas":list(s["areas"].values()),"floors":list(s["floors"].values())}))';const child=spawn('/usr/bin/python3',['-c',code],{stdio:['ignore','pipe','ignore'],env:process.env});let out='',done=false;const finish=v=>{if(done)return;done=true;clearTimeout(timer);if(v){metadata=v;at=Date.now()}resolve(v)};const timer=setTimeout(()=>{child.kill('SIGKILL');finish(null)},2500);child.stdout.on('data',x=>{out+=x;if(out.length>200000){child.kill('SIGKILL');finish(null)}});child.on('error',()=>finish(null));child.on('close',()=>{try{finish(JSON.parse(out))}catch{finish(null)}})}).finally(()=>pending=null);return pending;
}
export async function resolveReportScope(query,args){const registry=await catalog();if(!registry)throw new Error('Cannot verify area/floor scope yet; use the cloud recovery budget to retry this unsent read.');return chooseReportScope(query,args,registry);}

export async function namedStatusTarget(query){
 if(!isSimpleStatusQuery(query))return null;
 const m=String(query).trim().replace(/[.!?]+$/,'').match(/^(?:(?:what(?:'s| is)|show)\s+(?:the\s+)?)?(.+?)\s+(?:status|state)$/i);if(!m)return null;
 const subject=norm(m[1]);
 try{const registry=await catalog();if(!registry)return null;if([...registry.areas,...registry.floors].some(r=>[r.name,...(r.aliases||[])].filter(Boolean).some(n=>norm(n)===subject)))return null;
  const remote=JSON.parse(readFileSync(homedir()+'/llm-server/ha-remote.json','utf8'));const response=await fetch(new URL(remote.url).origin+'/api/states',{headers:{authorization:'Bearer '+process.env.HA_TOKEN},signal:AbortSignal.timeout(1500)});if(!response.ok)return null;
  const matches=(await response.json()).filter(e=>norm(e.attributes?.friendly_name||'')===subject);if(matches.length!==1)return null;const e=matches[0];return{name:e.attributes.friendly_name,domain:[e.entity_id.split('.')[0]],entityID:e.entity_id};
 }catch{return null;}
}
