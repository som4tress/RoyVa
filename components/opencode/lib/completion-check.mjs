import {readFileSync,writeFileSync,mkdirSync,renameSync,rmSync,appendFileSync} from 'node:fs';
import {homedir} from 'node:os';import {createHash,randomUUID} from 'node:crypto';
import {onDiscard} from './session-lifecycle.mjs';
const root=homedir()+'/.local/state/opencode/completion-check';
const hash=s=>createHash('sha256').update(s).digest('hex');
const file=id=>root+'/'+hash(id)+'.json';
export const canonical=text=>String(text||'').normalize('NFKC').trim().replace(/^```(?:text)?\s*|\s*```$/g,'').replace(/^["'“”‘’]+|["'“”‘’]+$/g,'').replace(/\s+/g,' ').toLowerCase();
export function currentRequest(body){for(const m of [...(body.messages||[])].reverse()){const text=typeof m.content==='string'?m.content:Array.isArray(m.content)?m.content.filter(p=>p.type==='text').map(p=>p.text).join('\n'):'';if(m.role==='user'&&text&&!text.startsWith('[RECENT CONVERSATION MEMORY:')&&!text.startsWith('<system-update>'))return text;}return '';}
export function readCompletionCheck(id,task){try{const d=JSON.parse(readFileSync(file(id),'utf8'));return !task||d.taskHash===hash(canonical(task))?d:null;}catch{return null;}}
export function clearCompletionCheck(id){rmSync(file(id),{force:true});}
export function noteCompletionFailure(id,task,reason,provider){
 const old=readCompletionCheck(id,task);const attempts=(old?.attempts||0)+1;
 const d={taskHash:hash(canonical(task)),reason,attempts,provider,route:attempts>=2&&provider==='local'?'cloud':null,at:Date.now()};
 mkdirSync(root,{recursive:true,mode:0o700});const p=file(id),tmp=p+'.'+randomUUID();writeFileSync(tmp,JSON.stringify(d),{mode:0o600});renameSync(tmp,p);
 appendFileSync(root+'/audit.jsonl',JSON.stringify({sessionHash:hash(id),...d})+'\n',{mode:0o600});return d;
}
export function completionProblem(body,answer){
 const task=currentRequest(body),prompt=canonical(task),text=canonical(answer);
 const requestedLiteral=/\b(?:repeat|echo|quote|copy)\b|\b(?:reply|respond|return|print|say)\s+(?:exactly|verbatim|with)\b/i.test(task);
 if(prompt.length>20&&prompt.split(' ').length>=5&&text===prompt&&!requestedLiteral)return 'prompt_echo';
 // A named source is an evidence claim, not proof that retrieval happened.
 // Inspect only this request's tool results; prior model prose is not evidence.
 let boundary=-1;for(let i=(body.messages||[]).length-1;i>=0;i--){const m=body.messages[i];if(m.role==='user'&&currentRequest({messages:[m]})===task){boundary=i;break;}}
 const results=(body.messages||[]).slice(boundary+1).filter(m=>m.role==='tool');
 const evidence=results.some(m=>!['discover_capabilities'].includes((body.messages||[]).flatMap(x=>x.tool_calls||[]).find(c=>c.id===m.tool_call_id)?.function?.name));
 const sourceClaim=/(?:^|\n)\s*(?:\*{0,2})source(?:s)?\s*(?:\*{0,2})\s*:|\b(?:i|we)\s+(?:queried|fetched|retrieved|called|checked)\s+(?:the\s+)?(?:api|database|live\s+data)\b/i.test(answer);
 if(sourceClaim&&!evidence&&body.tools?.some(t=>t.function?.name==='discover_capabilities'))return 'source_claim_without_evidence';
 // A capability limitation requires checking actual capabilities. Coverage,
 // safety refusals and missing private data are not capability-denial failures.
 const restriction=/\b(?:i|we)\s+(?:can only|only have|only support|cannot access|can'?t access|do not have|don'?t have|cannot browse|can'?t browse)\b/i.test(answer);
 const tools=/\b(?:tools?|capabilities|browse|internet|external\s+(?:data|forecasts?|sources?)|web access)\b/i.test(answer);
 const checked=(body.messages||[]).some(m=>(m.tool_calls||[]).some(c=>/^(?:discover_capabilities|websearch|webfetch)$/.test(c.function?.name)));
 if(restriction&&tools&&!checked&&body.tools?.some(t=>t.function?.name==='discover_capabilities'))return 'unchecked_capability_refusal';
 return null;
}
export function wireSummary(wire){
 let answer='',toolCalls=false,finished=false,usage=null;
 const take=j=>{if(j.usage)usage=j.usage;for(const c of j.choices||[]){const m=c.message||c.delta||{};if(typeof m.content==='string')answer+=m.content;if(m.tool_calls?.length)toolCalls=true;if(c.finish_reason==='stop')finished=true;}};
 try{take(JSON.parse(wire));}catch{for(const line of wire.split('\n'))if(line.startsWith('data:'))try{take(JSON.parse(line.slice(5)))}catch{}}
 return {answer,toolCalls,finished,usage};
}
export function discoveryContinuation(wire,model){
 const call={id:'call_check_'+randomUUID().replaceAll('-',''),type:'function',function:{name:'discover_capabilities',arguments:JSON.stringify({limit:6})}};
 try{const j=JSON.parse(wire);j.choices[0].message={...j.choices[0].message,content:null,tool_calls:[call]};j.choices[0].finish_reason='tool_calls';return JSON.stringify(j);}catch{}
 const output=[];let usage=null,id='completion-check';
 // Retain provider reasoning fields needed for subsequent tool continuations;
 // suppress only the invalid visible answer and its stop marker.
 for(const line of wire.split('\n')){
  if(!line.startsWith('data:'))continue;let j;try{j=JSON.parse(line.slice(5))}catch{continue;}
  if(j.id)id=j.id;if(j.usage){usage=j.usage;delete j.usage;}
  if(!j.choices?.length)continue;
  for(const c of j.choices){if(c.delta)delete c.delta.content;c.finish_reason=null;}
  output.push('data: '+JSON.stringify(j)+'\n\n');
 }
 const chunk=(delta,finish_reason=null)=>({id,object:'chat.completion.chunk',model,choices:[{index:0,delta,finish_reason}]});
 output.push('data: '+JSON.stringify(chunk({tool_calls:[{index:0,...call}]}))+'\n\n','data: '+JSON.stringify(chunk({},'tool_calls'))+'\n\n');
 if(usage)output.push('data: '+JSON.stringify({id,object:'chat.completion.chunk',model,choices:[],usage})+'\n\n');
 output.push('data: [DONE]\n\n');return output.join('');
}
onDiscard(clearCompletionCheck);
