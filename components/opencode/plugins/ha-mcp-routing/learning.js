import {readFileSync,writeFileSync,renameSync,mkdirSync,rmdirSync,statSync} from 'node:fs';
import {dirname} from 'node:path';
import {createHash} from 'node:crypto';
const STOP=new Set('a an the please kindly me my you your i we our us it is are was were be been being what whats how hows could can would will tell say show give let know about of for in at to from with current currently status looking look doing'.split(' '));
const POLARITY=new Set('on off not never no make enable disable run trigger activate deactivate lock unlock open close start stop turn switch set dim brighten increase decrease toggle'.split(' '));
export function tokens(text){return [...new Set(text.normalize('NFKC').toLowerCase().replace(/[’']/g,"'").replace(/\b(\w+)'s\b/g,'$1').replace(/\bdon't\b/g,'do not').match(/[a-z0-9_]+/g)||[])].filter(t=>!STOP.has(t)).sort();}
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const polarity=text=>tokens(text).filter(t=>POLARITY.has(t));
function read(path){try{const d=JSON.parse(readFileSync(path,'utf8'));return d.version===1&&Array.isArray(d.routes)?d:{version:1,routes:[]};}catch{return {version:1,routes:[]};}}
export function findLearned(path,text){
 const query=tokens(text);if(!query.length)return null;
 const set=new Set(query),p=polarity(text);
 const matches=read(path).routes.filter(r=>r.enabled!==false&&same(r.polarity,p)&&r.anchors.every(x=>set.has(x))).map(r=>{
  const union=new Set([...query,...r.tokens]);const common=r.tokens.filter(x=>set.has(x)).length;
  return {route:r,score:common/union.size};
 }).filter(x=>x.score>=0.95).sort((a,b)=>b.score-a.score);
 if(!matches.length)return null;
 if(matches[1]&&matches[0].route.taskKey!==matches[1].route.taskKey&&matches[0].score-matches[1].score<0.05)return null;
 return matches[0];
}
export function candidateFromSuccess({text,task,child}){
 if(!text||!task||/\b(diagnostic|routing test|do not learn|missing_entity|video|footage|clip|camera|ring|doorbell)\b/i.test(text))return null;
 const assistants=child.filter(m=>m.type==='assistant');
 if(!assistants.length||assistants.some(m=>!['vllm','evo-agent'].includes(m.model?.providerID)||m.error))return null;
 const calls=assistants.flatMap(m=>(m.content||[]).filter(c=>c.type==='tool'));
 if(!calls.length||calls.some(c=>c.state?.status!=='completed'||!/^(home[-_]assistant_|ha[-_]history_)/.test(c.name||'')))return null;
 for(const call of calls){
  const state=call.state||{};const content=Array.isArray(state.content)?state.content:[];
  const payloads=[state.output,...content.map(c=>c.text)].filter(x=>typeof x==='string');
  for(const payload of payloads){try{const data=JSON.parse(payload);if(data?.error||data?.logbook_error||data?.isError)return null;}catch{}}
 }

 const sourceTokens=tokens(text);if(sourceTokens.length<2||sourceTokens.length>16)return null;
 const names=calls.flatMap(c=>{const a=c.state?.input||{};return ['name','area','floor','person'].flatMap(k=>typeof a[k]==='string'?[a[k]]:[]);});
 let anchors=[...new Set(names.flatMap(tokens).filter(t=>sourceTokens.includes(t)))].filter(t=>!POLARITY.has(t)).sort();
 if(!anchors.length && calls.some(c=>/get_on_entities_with_context$/.test(c.name)))anchors=sourceTokens.filter(t=>['entities','devices','lights','switches','fans'].includes(t));
 if(!anchors.length)return null;
 const unique=[...new Set(calls.map(c=>c.name))];
 const readOnly=unique.every(n=>/GetLiveContext$|GetDateTime$|search_media$|^ha[-_]history_/.test(n));
 if(readOnly && polarity(text).some(t=>['turn','switch','set','enable','disable','run','trigger','activate','deactivate','lock','unlock','open','close','start','stop','dim','brighten','increase','decrease','toggle','make'].includes(t)))return null;
 if(!readOnly && !polarity(text).some(t=>!['on','off','not','never','no'].includes(t)))return null;
 if(/\b(today|yesterday|tonight|tomorrow|now)\b/i.test(text))task=task.replace(/\b20\d{2}-\d{2}-\d{2}\b/g,'the date requested now');
 const kind=unique.every(n=>/^ha[-_]history_/.test(n))?'history':'devices';
 const taskKey=createHash('sha256').update(JSON.stringify(calls.map(c=>({name:c.name,input:c.state.input})))).digest('hex').slice(0,16);
 const id=createHash('sha256').update(sourceTokens.join(' ')+'|'+taskKey).digest('hex').slice(0,16);
 return {id,enabled:true,readOnly,example:text,tokens:sourceTokens,polarity:polarity(text),anchors,kind,task,taskKey,requiredTool:unique.find(n=>/get_on_entities_with_context$/.test(n)) || calls[0].name,target:names.includes('Den Switch')?'Den Switch':undefined,tools:unique,createdAt:new Date().toISOString(),lastVerifiedAt:new Date().toISOString(),verifiedSuccesses:1};
}
async function updateStore(path,change){
 mkdirSync(dirname(path),{recursive:true,mode:0o700});const lock=path+'.lock';let held=false;
 for(let i=0;i<100;i++){
  try{mkdirSync(lock,{mode:0o700});held=true;break;}catch(e){if(e.code!=='EEXIST')throw e;try{if(Date.now()-statSync(lock).mtimeMs>30000)rmdirSync(lock);}catch{}await new Promise(r=>setTimeout(r,20));}
 }
 if(!held)throw new Error('Learned route store is busy');
 try{
  const d=read(path);change(d);
  d.routes=d.routes.slice(-200);d.updatedAt=new Date().toISOString();
  const temporary=path+'.'+process.pid+'.tmp';writeFileSync(temporary,JSON.stringify(d,null,2)+'\n',{mode:0o600});renameSync(temporary,path);return true;
 }finally{rmdirSync(lock);}
}

export async function remember(path,candidate){
 if(!candidate)return false;
 return updateStore(path,d=>{
  const old=d.routes.find(r=>r.id===candidate.id);
  if(old){old.lastVerifiedAt=candidate.lastVerifiedAt;old.verifiedSuccesses=(old.verifiedSuccesses||0)+1;}
  else d.routes.push(candidate);
 });
}
export async function disableLearned(path,id,reason){
 return updateStore(path,d=>{
  const route=d.routes.find(r=>r.id===id);
  if(route){route.enabled=false;route.disabledAt=new Date().toISOString();route.disabledReason=reason;}
 });
}
