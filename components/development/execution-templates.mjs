import {readFileSync,writeFileSync,renameSync,mkdirSync,appendFileSync,existsSync,statSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {homedir} from 'node:os';
import {dirname} from 'node:path';
import {spawn} from 'node:child_process';
import {renderReport} from './ha-reports.mjs';
const ROOT=homedir()+'/.config/opencode';
export const STORE=homedir()+'/.local/share/opencode/procedures/templates.json';
const FILES=['mcp/ha_template_runner.py','mcp/ha_history.py','mcp/ha_device_status.py','mcp/ha_status_report.py','mcp/ha_mcp_transport.py','instructions/home-assistant.md','instructions/ha-compact.md','lib/execution-templates.mjs','lib/ha-reports.mjs'];
const SUPPORTED=new Set(['ha-history_get_device_status','ha-history_get_device_status_report','ha-history_get_visited_locations','home-assistant_intent__HassTurnOn','home-assistant_intent__HassTurnOff']);
const EXTENSIONS=new Map(),EXTRA_FILES=new Set();
export function registerExecutionAdapter(adapter,modulePath){
 if(!adapter||typeof adapter.id!=='string'||!Array.isArray(adapter.tools)||!adapter.tools.length||typeof adapter.run!=='function'||typeof adapter.format!=='function')throw new Error('Invalid execution adapter');
 if(adapter.tools.some(t=>typeof t!=='string'||SUPPORTED.has(t)))throw new Error('Adapter tool conflicts with an existing adapter');
 for(const tool of adapter.tools){SUPPORTED.add(tool);EXTENSIONS.set(tool,adapter)}
 if(modulePath)EXTRA_FILES.add(modulePath);
 for(const file of adapter.fingerprintFiles||[])EXTRA_FILES.add(file.startsWith('/')?file:ROOT+'/'+file);
}
const LOOKUPS=new Set(['home-assistant_homeassistant__GetLiveContext','ha-history_get_device_status']);
const sha=s=>createHash('sha256').update(s).digest('hex');
export const queryKey=text=>String(text).normalize('NFKC').replace(/’/g,"'").toLowerCase().trim().replace(/[.!?]+$/g,'').replace(/\s+/g,' ');
const codeRead=p=>{if(statSync(p).size>4*1024*1024)throw new Error('Adapter dependency too large');return readFileSync(p)};
export function fingerprint(){try{return sha(FILES.map(p=>codeRead(ROOT+'/'+p)).concat([...EXTRA_FILES].map(p=>codeRead(p)),[readFileSync(homedir()+'/llm-server/ha-remote.json'),existsSync(ROOT+'/execution-adapters.json')?readFileSync(ROOT+'/execution-adapters.json'):Buffer.from('{}')]).map(x=>sha(x)).join('|'))}catch{return null}}
function validRecipe(recipe){
 if(!recipe||!SUPPORTED.has(recipe.tool)||!['read','write'].includes(recipe.kind))return false;
 const adapter=EXTENSIONS.get(recipe.tool);
 if(adapter)return recipe.adapter===adapter.id&&((adapter.writeTools||[]).includes(recipe.tool)===(recipe.kind==='write'));
 return /HassTurn(?:On|Off)$/.test(recipe.tool)===(recipe.kind==='write');
}
function readStore(path){try{const d=JSON.parse(readFileSync(path,'utf8'));return d.version===1&&Array.isArray(d.templates)?{...d,templates:d.templates.filter(t=>t&&typeof t.key==='string'&&typeof t.query==='string'&&t.recipe)}:{version:1,templates:[]}}catch{return {version:1,templates:[]}}}
function writeStore(path,d){mkdirSync(dirname(path),{recursive:true,mode:0o700});const tmp=path+'.'+process.pid+'.tmp';writeFileSync(tmp,JSON.stringify(d,null,2),{mode:0o600});renameSync(tmp,path)}
export function saveTemplate(query,recipe,{path=STORE,code=fingerprint(),now=Date.now()}={}){
 if(!code||!validRecipe(recipe))return false;
 recipe={...recipe,args:{...recipe.args}};delete recipe.query;
 const adapter=EXTENSIONS.get(recipe.tool);if(adapter&&(recipe.adapter!==adapter.id||((adapter.writeTools||[]).includes(recipe.tool)!==(recipe.kind==='write'))))return false;
 const d=readStore(path),key=sha(queryKey(query)),signature=sha(JSON.stringify(recipe));const prior=d.templates.find(t=>t.key===key);
 if(prior&&prior.signature!==signature&&prior.code===code){prior.enabled=false;prior.reason='Conflicting verified interpretations';writeStore(path,d);return false;}
 const entry={key,query:queryKey(query),recipe,signature,code,enabled:true,created:prior?.created||now,verifiedAt:now,hits:prior?.hits||0};
 if(prior){if(prior.enabled===false&&prior.reason==='Conflicting verified interpretations')return false;Object.assign(prior,entry)}else d.templates.push(entry);
 d.templates=d.templates.slice(-1500);writeStore(path,d);return true;
}
export function findTemplate(query,{path=STORE,code=fingerprint(),now=Date.now()}={}){
 if(!code)return null;const key=sha(queryKey(query));
 return readStore(path).templates.find(t=>t.key===key&&t.enabled&&t.code===code&&validRecipe(t.recipe)&&now-t.verifiedAt<=30*86400000&&now>=t.verifiedAt)||null;
}
function updateTemplate(key,update,path=STORE){try{const d=readStore(path),t=d.templates.find(x=>x.key===key);if(t){Object.assign(t,update);writeStore(path,d)}}catch{}}
function audit(event,path=STORE){try{mkdirSync(dirname(path),{recursive:true,mode:0o700});appendFileSync(dirname(path)+'/execution.jsonl',JSON.stringify({at:new Date().toISOString(),...event})+'\n',{mode:0o600})}catch{}}
export function currentTurn(body,userQuery){
 const msgs=body.messages||[];let index=-1;for(let i=msgs.length-1;i>=0;i--)if(msgs[i].role==='user'){index=i;break;}
 if(index<0)return null;
 let content=msgs[index].content;
 if(Array.isArray(content)){if(content.some(p=>p.type!=='text'))return null;content=content.map(p=>p.text||'').join('\n');}
 if(typeof userQuery==='string'&&userQuery.length)content=userQuery;
 if(typeof content!=='string'||content.length>600)return null;
 const tail=msgs.slice(index+1),calls=tail.flatMap(m=>m.role==='assistant'?(m.tool_calls||[]):[]),results=tail.filter(m=>m.role==='tool');
 const priorConstraints=msgs.slice(0,index).filter(m=>m.role==='user').some(m=>/do not|don't|never|unless|forbid|permission|class|sleeping/i.test(typeof m.content==='string'?m.content:JSON.stringify(m.content)));
 return {query:content,tail,calls,results,priorConstraints};
}
export function decodeResult(value,depth=0){
 if(depth>5)return null;
 if(typeof value==='string'){try{return decodeResult(JSON.parse(value),depth+1)}catch{return null}}
 if(Array.isArray(value)){for(const part of value){const d=decodeResult(part?.text??part,depth+1);if(d)return d;}return null}
 if(!value||typeof value!=='object'||value.isError||value.error)return null;
 if(value.content)return decodeResult(value.content,depth+1);
 return value;
}
export function candidateFromTurn(body,userQuery){
 const turn=currentTurn(body,userQuery);if(!turn?.results.length||body.messages.at(-1)?.role!=='tool')return null;
 const last=turn.results.at(-1),call=turn.calls.find(c=>c.id===last.tool_call_id);
 if(!call||!SUPPORTED.has(call.function?.name))return null;
 if(['ha-history_get_device_status','ha-history_get_visited_locations'].includes(call.function.name)&&turn.calls.length!==1)return null;
 if(turn.priorConstraints&&/HassTurn(?:On|Off)$/.test(call.function.name))return null;
 const adapter=EXTENSIONS.get(call.function.name),lookups=adapter?new Set(adapter.lookupTools||[]):LOOKUPS;
 if(turn.calls.some(c=>c.id!==call.id&&!lookups.has(c.function?.name)))return null;
 // All earlier calls must have their own completed result; no pending parallel work.
 if(turn.calls.some(c=>!turn.results.some(r=>r.tool_call_id===c.id)))return null;
 let args;try{args=JSON.parse(call.function.arguments||'{}')}catch{return null}
 const data=adapter?.decode?adapter.decode(last.content):decodeResult(last.content);if(!data)return null;
 return {operation:'certify',query:turn.query,tool:call.function.name,args,data};
}
export function runProcedure(request,{timeoutMs=request.operation==='execute'&&request.recipe?.kind==='write'?25000:10000}={}){
 const adapter=EXTENSIONS.get(request.tool||request.recipe?.tool);if(adapter)return Promise.resolve(adapter.run(request)).catch(()=>({ok:false,message:'Registered adapter failed.'}));
 return new Promise(resolve=>{
  const child=spawn('/usr/bin/python3',[ROOT+'/mcp/ha_template_runner.py'],{stdio:['pipe','pipe','pipe'],env:process.env,shell:false});let out='',done=false;
  const finish=value=>{if(done)return;done=true;clearTimeout(timer);resolve(value)};
  const timer=setTimeout(()=>{child.kill('SIGKILL');finish({ok:false,write_uncertain:request.operation==='execute'&&request.recipe?.kind==='write',message:'Procedure execution timed out; check current state before retrying.'})},timeoutMs);
  child.stdout.on('data',chunk=>{out+=chunk.toString();if(out.length>1024*1024){child.kill('SIGKILL');finish({ok:false,message:'Procedure result too large.'})}});
  child.stderr.on('data',()=>{});child.on('error',()=>finish({ok:false,message:'Procedure runner unavailable.'}));
  child.on('close',()=>{try{finish(JSON.parse(out))}catch{finish({ok:false,write_uncertain:request.operation==='execute'&&request.recipe?.kind==='write',message:'Procedure result could not be verified.'})}});
  child.stdin.on('error',()=>{});child.stdin.end(JSON.stringify(request));
 });
}
const cell=v=>String(v??'unknown').replace(/[\n\r\t]/g,' ').replace(/\|/g,'\\|').slice(0,200);
export function formatProcedure(tool,data,query=''){
 const adapter=EXTENSIONS.get(tool);if(adapter)return adapter.format(tool,data,query);
 if(tool==='ha-history_get_device_status_report')return renderReport(data);
 if(tool==='ha-history_get_device_status'){
  if(!Array.isArray(data?.matches)||!data.matches.length)return null;
  if(data.matches.length===1){const m=data.matches[0];return cell(m.name)+': '+cell(m.state)+'.';}
  return '| Device | Type | State |\n|---|---|---|\n'+data.matches.map(m=>'| '+[m.name,m.domain,m.state].map(cell).join(' | ')+' |').join('\n');
 }
 if(tool==='ha-history_get_visited_locations'){
  if(!Array.isArray(data?.recorded_locations))return null;
  const title=cell(data.person)+' — recorded locations on '+cell(data.date)+' (America/Los_Angeles)';
  if(!data.recorded_locations.length)return title+'\nNo named-zone visits were recorded. This does not prove no travel occurred.';
  if(/\b(timeline|when|times?|intervals?|detailed|chronological)\b/i.test(query)){
   const time=x=>{try{return new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(x))}catch{return 'unknown'}};
   return title+'\n\n| Recorded location | From (PT) | To (PT) |\n|---|---|---|\n'+data.recorded_locations.map(r=>'| '+[r.location,time(r.from),r.ongoing?'ongoing':time(r.to)].map(cell).join(' | ')+' |').join('\n')+'\n\nRecorded zones may include brief crossings.';
  }
  const names=[...new Set(data.recorded_locations.map(x=>x.location))];
  return title+'\n\n| Recorded location |\n|---|\n'+names.map(n=>'| '+cell(n)+' |').join('\n')+'\n\nRecorded zones may include brief crossings.';
 }
 if(/HassTurn(?:On|Off)$/.test(tool)&&typeof data?.name==='string'&&['on','off'].includes(data.state))return cell(data.name)+': '+data.state+'.';
 return null;
}
export async function tryExecutionTemplate(body,{run=runProcedure,path=STORE,code=fingerprint(),now=Date.now(),userQuery}={}){
 const turn=currentTurn(body,userQuery);if(!turn||turn.calls.length||turn.results.length)return null;
 const template=findTemplate(turn.query,{path,code,now});if(!template)return null;
 if(template.recipe.kind==='write'&&turn.priorConstraints)return null;
 const started=Date.now(),result=await run({operation:'execute',query:turn.query,recipe:template.recipe});
 if(!result.ok){updateTemplate(template.key,{enabled:false,reason:result.message||'Revalidation failed'},path);audit({event:'template-invalidated',key:template.key,kind:template.recipe.kind,ms:Date.now()-started},path);return result.write_uncertain?{text:result.message,source:'uncertain-write',zeroLLM:true}:null;}
 const text=formatProcedure(template.recipe.tool,result.data,turn.query);if(text===null)return null;
 updateTemplate(template.key,{hits:template.hits+1,lastUsed:Date.now()},path);audit({event:'template-executed',key:template.key,kind:template.recipe.kind,ms:Date.now()-started},path);
 return {text,source:'verified-template',zeroLLM:true};
}
export async function learnExecutionTemplate(body,{run=runProcedure,path=STORE,code=fingerprint(),now=Date.now(),userQuery}={}){
 const candidate=candidateFromTurn(body,userQuery);if(!candidate)return null;
 const proof=await run(candidate);if(!proof.ok||!proof.recipe){audit({event:'template-not-certified',key:sha(queryKey(candidate.query)),tool:candidate.tool,reason:proof.message||'No proof'},path);return null;}
 if(proof.recipe.tool!==candidate.tool||!['read','write'].includes(proof.recipe.kind))return null;
 if(proof.recipe.kind==='write'&&currentTurn(body,userQuery)?.priorConstraints)return null;
 const saved=saveTemplate(candidate.query,proof.recipe,{path,code,now});
 const data=proof.data??(proof.recipe.kind==='write'?{name:proof.recipe.args.name,state:proof.recipe.desired}:candidate.data);
 const text=formatProcedure(candidate.tool,data,candidate.query);if(text===null)return null;
 audit({event:'template-certified',key:sha(queryKey(candidate.query)),kind:proof.recipe.kind,saved},path);
 return {text,source:'verified-tool-formatter',zeroLLM:false};
}

// Only explicitly enabled, local adapter modules are loaded. Captured shell/code
// records do not become executable merely because a prior tool call completed.
try{
 const manifest=JSON.parse(readFileSync(ROOT+'/execution-adapters.json','utf8'));
 for(const entry of manifest.version===1&&Array.isArray(manifest.adapters)?manifest.adapters:[]){
  if(entry.enabled!==true||!/^[-a-zA-Z0-9_]+\.mjs$/.test(entry.module||''))continue;
  const file=ROOT+'/lib/execution-adapters/'+entry.module;
  try{const mod=await import(file);registerExecutionAdapter(mod.default,file)}catch(error){console.log(JSON.stringify({event:'execution-adapter-disabled',module:entry.module,error:error?.name||'Error'}))}
 }
}catch{}
