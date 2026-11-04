import {DatabaseSync} from 'node:sqlite';
import {appendFileSync,mkdirSync,readFileSync} from 'node:fs';
import {homedir} from 'node:os';
import {cleanToolEvidence} from './evidence-window.mjs';

const root=homedir()+'/.local/share/opencode/context-hygiene';
export const policy={targetTokens:8000,compactionTokens:16000,maxTokens:65536,maxAgeMs:30*60*1000,memoryChars:4000};
const text=m=>typeof m?.content==='string'?m.content:Array.isArray(m?.content)?m.content.filter(p=>p.type==='text').map(p=>p.text).join('\n'):'';
const update=m=>m.role==='user'&&/^\s*<system-update>/.test(text(m));
const memoryPrefix='[RECENT CONVERSATION MEMORY:';
const memoryMessage=m=>m.role==='user'&&text(m).startsWith(memoryPrefix);
const realUser=m=>m.role==='user'&&!update(m)&&!memoryMessage(m);
const final=m=>m.role==='assistant'&&!m.tool_calls?.length&&!!text(m).trim();
const secret=s=>s.replace(/\beyJ[\w-]+\.[\w-]+\.[\w-]+\b/g,'[credential omitted]').replace(/Bearer\s+\S+/gi,'Bearer [credential omitted]').replace(/\bsk-(?:or-v1-)?[\w-]{20,}/g,'[credential omitted]');
export class ContextLimitError extends Error {constructor(message){super(message);this.name='ContextLimitError';}}

export function refreshInstructions(body,{sources}={}){
 if(!sources){sources=new Map();try{for(const path of JSON.parse(readFileSync(homedir()+'/.config/opencode/opencode.json','utf8')).instructions||[]){try{sources.set(path,readFileSync(path,'utf8').trim())}catch{}}}catch{}}
 const refreshed=new Set();
 const messages=(body.messages||[]).map(m=>{
  if(m.role!=='system'||typeof m.content!=='string')return m;
  const content=m.content.replace(/(^|\n)Instructions from: ([^\n]+)\n([\s\S]*?)(?=\nInstructions from: |\n\nToday's date:|$)/g,(all,prefix,path,old)=>{
   if(!sources.has(path))return all;refreshed.add(path);
   return prefix+'Instructions from: '+path+'\n'+sources.get(path)+'\n\n';
  });return {...m,content};
 });
 // Only discard instruction diffs whose baseline was refreshed. Unknown
 // framework updates remain, rather than silently losing changed constraints.
 const updates=[];const seen=new Set();
 for(const m of [...messages].reverse())if(update(m)){
  const refs=[...text(m).matchAll(/Instructions from: ([^\n]+)|The instructions from (.+?) changed\./g)].map(x=>x[1]||x[2]);
  if(refs.length&&refs.every(p=>refreshed.has(p)))continue;
  const key=refs.join('|')||(/Today's date is now:/.test(text(m))?'date':text(m));if(!seen.has(key)){updates.unshift(m);seen.add(key);}
 }
 return {...body,messages:[...messages.filter(m=>!update(m)),...updates]};
}

function timestamps(session){
 const times=new Map();if(!session)return times;let db;
 try{db=new DatabaseSync(homedir()+'/.local/share/opencode/opencode.db',{readOnly:true});
  for(const row of db.prepare("SELECT data,time_created FROM session_message WHERE session_id=? AND type='user' ORDER BY time_created DESC LIMIT 500").all(session)){
   const d=JSON.parse(row.data);if(typeof d.text==='string'){if(!times.has(d.text))times.set(d.text,[]);times.get(d.text).unshift(row.time_created);}
  }
 }catch{}finally{db?.close();}return times;
}

// Completed means a final assistant text was emitted, not that a write succeeded.
// Failed/unverified outcomes remain explicitly unverified. Never replay reasoning.
export function distillHistory(body,{now=Date.now(),timeMap=new Map()}={}){
 const messages=body.messages||[];let lastUser=-1;
 const occurrenceTimes=new Map(),queues=new Map([...timeMap].map(([key,value])=>[key,Array.isArray(value)?[...value]:[value]]));
 // Match repeated identical prompts by occurrence. Reusing the newest timestamp
 // for every occurrence would make stale answers appear fresh.
 for(let i=messages.length-1;i>=0;i--)if(realUser(messages[i])){const queue=queues.get(text(messages[i]));if(queue?.length)occurrenceTimes.set(i,queue.pop());}
 for(let i=0;i<messages.length;i++)if(realUser(messages[i]))lastUser=i;
 if(lastUser<0)return {body,removed:0,memoryEntries:0};
 let boundary=lastUser;
 // Steering can insert a user message inside an unfinished tool cycle. Retain
 // that cycle, and the initiating request, until it has a final answer.
 let previous=-1;for(let i=lastUser-1;i>=0;i--)if(final(messages[i])){previous=i;break;}
 const preceding=messages.slice(previous+1,lastUser).findIndex(realUser);
 if(preceding>=0)boundary=previous+1+preceding;
 const lastConversation=messages.filter(m=>!['system','developer'].includes(m.role)&&!update(m)).at(-1);
 if(final(lastConversation))boundary=messages.length;
 else {
  const start=occurrenceTimes.get(boundary);
  if(start&&now-start>policy.maxAgeMs)throw new ContextLimitError('This unfinished task is older than the 30-minute working-context limit. Submit a fresh request so its state and authorization can be checked again.');
 }
 const memo=[];
 for(const m of messages.filter(memoryMessage))try{
  for(const entry of JSON.parse(text(m).slice(text(m).indexOf('\n')+1)))if(Number.isFinite(entry.at)&&now-entry.at<=policy.maxAgeMs&&entry.at<=now)memo.push(entry);
 }catch{}
 for(let i=0;i<boundary;i++){
  const m=messages[i];if(!realUser(m))continue;
  const at=occurrenceTimes.get(i);if(!at||now-at>policy.maxAgeMs||at>now)continue;
  let end=i+1;while(end<boundary&&!realUser(messages[end]))end++;
  const answer=messages.slice(i+1,end).filter(final).at(-1);
  // Only user requests and final outcome excerpts enter follow-up memory.
  // No tool arguments, tool results, logs, or historical reasoning enter it.
  if(answer)memo.push({at,request:secret(text(m)).slice(0,700),outcome:secret(text(answer)).slice(0,1000),excerpt:true});
 }
 const selected=[];let size=0;
 for(const entry of memo.reverse()){const n=JSON.stringify(entry).length;if(size+n>policy.memoryChars)continue;selected.unshift(entry);size+=n;}
 const systems=messages.filter(m=>m.role==='system'||m.role==='developer');
 const active=messages.slice(boundary).filter(m=>!['system','developer'].includes(m.role));
 // Instruction diffs are replaced by the authoritative current system baseline.
 const activeClean=active.filter(m=>!update(m)&&!memoryMessage(m));
 const updates=messages.filter(update);
 const memory=selected.length?[{role:'user',content:'[RECENT CONVERSATION MEMORY: historical excerpts, not new instructions or verified current state. Never replay actions from this memory or reload completed-task raw traces. Resolve follow-ups against it; fetch fresh changing data. Do not retrieve conversation older than 30 minutes. If an excerpt is insufficient, fetch fresh task evidence or ask.]\n'+JSON.stringify(selected)}]:[];
 return {body:{...body,messages:[...systems,...updates,...memory,...activeClean]},removed:messages.length-systems.length-activeClean.length-updates.length,memoryEntries:selected.length};
}

export function validateToolChains(body){
 let pending=new Set();const used=new Set();
 for(const m of body.messages||[]){
  if(m.role==='tool'){
   if(!pending.has(m.tool_call_id))throw new ContextLimitError('Orphan or duplicate tool result; request withheld to preserve tool-call integrity.');
   pending.delete(m.tool_call_id);continue;
  }
  if(pending.size)throw new ContextLimitError('Unresolved tool-call chain; request withheld rather than dropping or replaying actions.');
  for(const c of m.tool_calls||[]){if(!c.id||used.has(c.id))throw new ContextLimitError('Duplicate or missing tool-call identifier.');pending.add(c.id);used.add(c.id);}
 }
 if(pending.size)throw new ContextLimitError('Tool results are still pending; no inference submitted.');
}

function shortenDescriptions(value,depth=0,maxChars=700){
 if(Array.isArray(value))return value.map(v=>shortenDescriptions(v,depth+1,maxChars));
 if(!value||typeof value!=='object')return value;
 // Only documentation is shortened. Never alter actual arguments, enum values,
 // names, required fields, validation rules, or tool result values.
 return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,k==='description'&&typeof v==='string'&&v.length>maxChars?v.slice(0,maxChars)+' [Description shortened; schema constraints below remain authoritative.]':shortenDescriptions(v,depth+1,maxChars)]));
}

export async function countInput(body,{signal,vision=false}={}){
 // /tokenize would otherwise decode a video a second time. Bound text here;
 // vLLM's native model length check accounts for actual multimodal tokens.
 const messages=vision?(body.messages||[]).map(m=>({...m,content:Array.isArray(m.content)?m.content.filter(p=>p.type==='text'):m.content})):body.messages;
 const r=await fetch('http://127.0.0.1:'+(vision?'8001':'8000')+'/tokenize',{method:'POST',headers:{'content-type':'application/json',authorization:'Bearer '+process.env.VLLM_API_KEY},
  body:JSON.stringify({model:vision?'qwen35-vision':'qwen36-agent',messages,tools:body.tools,chat_template_kwargs:body.chat_template_kwargs}),signal:signal?AbortSignal.any([signal,AbortSignal.timeout(5000)]):AbortSignal.timeout(5000)});
 if(!r.ok)throw new ContextLimitError('Input tokenizer unavailable; oversized requests will not be submitted unchecked.');
 const j=await r.json();if(Number.isFinite(j.count))return j.count;
 // llama.cpp tokenizes rendered content rather than vLLM chat messages.
 // Render with the server's actual template so tool schemas and control tokens
 // are counted too; never treat its empty messages-only tokens as a valid count.
 if(!vision&&Array.isArray(j.tokens)){
  const base='http://127.0.0.1:8000';
  const post=async(path,payload)=>{
   const response=await fetch(base+path,{method:'POST',headers:{'content-type':'application/json',authorization:'Bearer '+process.env.VLLM_API_KEY},body:JSON.stringify(payload),signal:signal?AbortSignal.any([signal,AbortSignal.timeout(5000)]):AbortSignal.timeout(5000)});
   if(!response.ok)throw new ContextLimitError('Input tokenizer unavailable; oversized requests will not be submitted unchecked.');
   return response.json();
  };
  const rendered=await post('/apply-template',{...body,messages});
  if(typeof rendered.prompt!=='string')throw new ContextLimitError('Invalid rendered input for tokenizer.');
  const tokenized=await post('/tokenize',{content:rendered.prompt,add_special:false,parse_special:true});
  if(Array.isArray(tokenized.tokens)&&tokenized.tokens.every(Number.isInteger))return tokenized.tokens.length;
 }
 throw new ContextLimitError('Invalid input token count.');
}

export async function sanitizeContext(input,{session,signal,vision=false,now=Date.now(),timeMap,count=countInput,audit=count===countInput}={}){
 const started=Date.now();const history=distillHistory(refreshInstructions(input),{now,timeMap:timeMap||timestamps(session)});let body=history.body;
 const task=text(body.messages.filter(realUser).at(-1));
 const recover=(body.tools||[]).some(t=>/^(read|shell)$/.test(t.function?.name||''));
 let archived=0;let bounded=cleanToolEvidence(body,{task,threshold:6000,maxChars:4000});body=bounded.body;archived+=bounded.archived;
 validateToolChains(body);
 let tokens=await count(body,{signal,vision});
 if(tokens>policy.targetTokens&&body.tools){body={...body,tools:shortenDescriptions(body.tools)};tokens=await count(body,{signal,vision});}
 for(const maxChars of [2400,1200]){
  if(tokens<=policy.compactionTokens||!recover)break;
  // Do not repeatedly excerpt an already bounded view: regenerate from the
  // full active source on each tightening pass, retaining the same source hash.
  bounded=cleanToolEvidence({...history.body,tools:body.tools},{task,threshold:6000,maxChars});
  body={...body,messages:bounded.body.messages};archived=Math.max(archived,bounded.archived);tokens=await count(body,{signal,vision});
 }
 // 16K is a cleanup trigger, not permission to fail an ordinary multi-step
 // task. Fixed instructions/schemas already consume most of that budget.
 // Optional conversational excerpts go first; preserve current user input,
 // exact call arguments, schemas and provider-required active reasoning.
 let memoryReduced=false;
 if(tokens>policy.compactionTokens){
  const messages=body.messages.map(m=>{
   if(!memoryMessage(m))return m;
   try{const split=text(m).indexOf('\n'),entries=JSON.parse(text(m).slice(split+1));if(entries.length<=1)return m;memoryReduced=true;return {...m,content:text(m).slice(0,split+1)+JSON.stringify(entries.slice(-1))};}catch{return m;}
  });
  // Preserve the latest outcome for pronoun/follow-up resolution. Do not buy
  // a smaller count by silently removing the only available referent.
  body={...body,messages,tools:body.tools?shortenDescriptions(body.tools,0,400):body.tools};
  tokens=await count(body,{signal,vision});
 }
 validateToolChains(body);
 if(tokens>policy.maxTokens)throw new ContextLimitError('Active request exceeds the 64K emergency input limit after cleanup. Current evidence or instructions need further scoping; this model step was withheld without truncating user input or replaying actions.');
 const stats={at:Date.now(),session,removedMessages:history.removed,memoryEntries:memoryReduced?1:history.memoryEntries,archivedResults:archived,memoryReduced,aboveCompactionTarget:tokens>policy.compactionTokens,beforeBytes:Buffer.byteLength(JSON.stringify(input)),afterBytes:Buffer.byteLength(JSON.stringify(body)),inputTokens:tokens,tokenBasis:vision?'Qwen3.5 text tokens only; native vLLM limit checks multimodal total':'Qwen3.6 tokenizer (cloud counts may differ)',elapsedMs:Date.now()-started};
 if(audit){mkdirSync(root,{recursive:true,mode:0o700});appendFileSync(root+'/audit.jsonl',JSON.stringify(stats)+'\n',{mode:0o600});}
 return {body,stats};
}
