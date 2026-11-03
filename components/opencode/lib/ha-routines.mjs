import {readFileSync,appendFileSync,mkdirSync,writeFileSync,renameSync} from 'node:fs';
import {homedir} from 'node:os';
import {createHash} from 'node:crypto';
import {matchRoutineNames} from './ha-intent.mjs';
const pending=new Map();
function connection(){const h=homedir();const remote=JSON.parse(readFileSync(h+'/llm-server/ha-remote.json','utf8'));let token=process.env.HA_TOKEN||readFileSync(h+'/llm-server/ha.env','utf8').match(/^HA_TOKEN=(.*)$/m)?.[1]?.replace(/^["']|["']$/g,'');return {base:new URL(remote.url).origin,token};}
export async function executeNamedRoutine(query,{session='',turn='',fetcher=fetch,connect=connection,audit=true}={}){
 if(!query||query.length>100)return null;
 const {base,token}=connect();if(!token)return null;
 let states;try{const r=await fetcher(base+'/api/states',{headers:{authorization:'Bearer '+token},signal:AbortSignal.timeout(1500)});if(!r.ok)return null;states=await r.json();}catch{return null;}
 const matches=matchRoutineNames(query,states);if(!matches.length)return null;
 if(matches.length!==1)return {text:'More than one HA routine matches. Please specify the automation, script, or scene.',ambiguous:true};
 const target=matches[0],domain=target.entity_id.split('.')[0],key=createHash('sha256').update(JSON.stringify([session,turn,query,target.entity_id])).digest('hex');
 if(pending.has(key))return pending.get(key).result;
 let record=null;
 if(audit){
  const dir=homedir()+'/.local/share/opencode/task-learning/routine-turns';mkdirSync(dir,{recursive:true,mode:0o700});record=dir+'/'+key+'.json';
  try{writeFileSync(record,JSON.stringify({at:Date.now(),entity_id:target.entity_id,started:true}),{mode:0o600,flag:'wx'});}catch(e){
   if(e.code!=='EEXIST')return {text:'Cannot safely record this routine invocation; no action was sent.',ok:false};
   try{const previous=JSON.parse(readFileSync(record,'utf8'));return previous.result||{text:'A previous trigger attempt for '+target.name+' has an uncertain result. I have not retried it.',entity_id:target.entity_id,uncertain:true,ok:false};}catch{return {text:'Cannot verify the previous routine attempt. I have not retried it.',uncertain:true,ok:false};}
  }
 }
 const job=(async()=>{
  const payload={entity_id:target.entity_id,...(domain==='automation'?{skip_condition:false}:{})};let result;
  try{const r=await fetcher(base+'/api/services/'+domain+'/'+(domain==='automation'?'trigger':'turn_on'),{method:'POST',headers:{authorization:'Bearer '+token,'content-type':'application/json'},body:JSON.stringify(payload),signal:AbortSignal.timeout(5000)});
   if(!r.ok){result={text:'HA did not confirm triggering '+target.name+' (HTTP '+r.status+'). I have not retried it.',entity_id:target.entity_id,uncertain:r.status>=500,ok:false};}
   else result={text:'Triggered '+target.name+' in Home Assistant. Its actions may still be running.',entity_id:target.entity_id,ok:true};
  }catch{result={text:'The trigger result for '+target.name+' is uncertain. I have not retried it.',entity_id:target.entity_id,uncertain:true,ok:false};}
  if(record)try{const temp=record+'.'+process.pid;writeFileSync(temp,JSON.stringify({at:Date.now(),entity_id:target.entity_id,result}),{mode:0o600});renameSync(temp,record);}catch{}
  if(audit)try{const root=homedir()+'/.local/share/opencode/task-learning';mkdirSync(root,{recursive:true,mode:0o700});appendFileSync(root+'/routine-executions.jsonl',JSON.stringify({at:Date.now(),session,turn,entity_id:target.entity_id,ok:!!result.ok,uncertain:!!result.uncertain})+'\n',{mode:0o600});}catch{}
  return result;
 })();pending.set(key,{at:Date.now(),result:job});for(const [k,v]of pending)if(Date.now()-v.at>1800000)pending.delete(k);return job;
}
