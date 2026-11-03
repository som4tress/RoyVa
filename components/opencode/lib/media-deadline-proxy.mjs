import {beginProcessing,endProcessing} from './processing-trace.mjs';
import {sanitizeContext,ContextLimitError} from './context-hygiene.mjs';
import {isDiscarded} from './discard-session.mjs';
import {snapshotCloudRequest,snapshotCloudResponse} from './cloud-payload-audit.mjs';
import {optimizeCloudRequest,forgetCloudSession} from './cloud-context-optimizer.mjs';
import {clearEvidenceMemo} from './evidence-window.mjs';
import {completionProblem,currentRequest,wireSummary,noteCompletionFailure,discoveryContinuation} from './completion-check.mjs';
import {formatNativeStatus,isSimpleStatusQuery} from './ha-native-status.mjs';
import {executeNamedRoutine} from './ha-routines.mjs';
import {cloudDirective} from './user-scope.mjs';
import {tryCalculation} from './execution-adapters/local-calculator.mjs';
import {randomUUID} from 'node:crypto';
import {completeTask,recordCloudCall} from './task-learning.mjs';
import {isCurrentLocationQuery} from './location-query.mjs';
import {tryExecutionTemplate,learnExecutionTemplate,currentTurn,saveTemplate,runProcedure} from './execution-templates.mjs';
import {reportFromRequest,reportWire} from './ha-reports.mjs';
import http from 'node:http';
import fsmod from 'node:fs';
import {once} from 'node:events';

/** Append "Usage (local): ..." to a finished local answer (JSON or SSE wire). */
function withLocalFooter(body,type){
 const k=n=>n>=1000?(n/1000).toFixed(1)+'k':String(n);
 const line=u=>{
  if(!u)return null;
  const cached=Number(u.prompt_tokens_details?.cached_tokens||0);
  const fresh=Math.max(0,Number(u.prompt_tokens||0)-cached);
  const out=Number(u.completion_tokens||0);
  const think=Number(u.completion_tokens_details?.reasoning_tokens||0);
  const parts=[`in ${k(fresh)} fresh / ${k(cached)} cached`,`out ${k(out)}`];
  if(think)parts.push(`think ${k(think)}`);
  return '\n\nUsage (local): '+parts.join(' \u00b7 ');
 };
 if(/event-stream/i.test(type)){
  const lines=body.split('\n'),out=[];let usage=null,finish=false,text='';
  for(const raw of lines){
   if(!raw.startsWith('data:')){out.push(raw);continue;}
   const data=raw.slice(5).trim();
   if(data==='[DONE]'){out.push(raw);continue;}
   let chunk;try{chunk=JSON.parse(data)}catch{out.push(raw);continue;}
   if(chunk.usage)usage=chunk.usage;
   const ch=chunk.choices?.[0];
   if(ch?.delta?.content)text+=ch.delta.content;
   if(ch?.delta?.tool_calls?.length||ch?.message?.tool_calls?.length)return body;
   if(ch?.finish_reason)finish=true;
   out.push(raw);
  }
  const footer=usage?line(usage):null;
  if(!footer||!text.trim())return body;
  const pos=out.lastIndexOf('data: [DONE]');
  const payload='data: '+JSON.stringify({choices:[{index:0,delta:{content:footer},finish_reason:null}]});
  if(pos>=0)out.splice(pos,0,payload,'');else out.push(payload,'');
  return out.join('\n');
 }
 try{
  const j=JSON.parse(body),msg=j.choices?.[0]?.message;
  if(!msg||typeof msg.content!=='string'||!msg.content.trim()||(msg.tool_calls&&msg.tool_calls.length))return body;
  const footer=line(j.usage);if(!footer)return body;
  msg.content=msg.content.trimEnd()+footer;
  return JSON.stringify(j);
 }catch{return body}
}


const HA_BASE='https://som4tress.duckdns.org:8123';
const PEOPLE={somdutta:'Somdutta',shobha:'Shobha',shubha:'Shobha',shivangsh:'Shivangsh',shivi:'Shivangsh'};
function haToken(){
 if(process.env.HA_TOKEN)return process.env.HA_TOKEN.trim();
 for(const f of ['/home/somdutta/.config/environment.d/90-ha-token.conf','/home/somdutta/.zshrc']){
  try{const m=fsmod.readFileSync(f,'utf8').match(/eyJ[A-Za-z0-9._-]{20,}/);if(m)return m[0];}catch{}
 }
 return null;
}
/** Deterministic "where is <person>" answer that always carries a Maps link. */
async function personLocationAnswer(query){
 try{
  const q=String(query||'').toLowerCase();
  if(!isCurrentLocationQuery(query,PEOPLE))return null;
  const who=Object.keys(PEOPLE).find(k=>new RegExp('\\b'+k+'\\b').test(q));
  if(!who)return null;
  const tok=haToken();if(!tok)return null;
  const r=await fetch(HA_BASE+'/api/states/person.'+who,{headers:{authorization:'Bearer '+tok},signal:AbortSignal.timeout(6000)});
  if(!r.ok)return null;
  const j=await r.json(),a=j.attributes||{};
  const name=a.friendly_name||PEOPLE[who];
  const known=j.state&&!['not_home','unknown','unavailable'].includes(j.state);
  let text=known?name+' is at '+j.state+'.':name+' is not in a named zone right now.';
  if(a.latitude!=null&&a.longitude!=null){
   const lat=Number(a.latitude).toFixed(6),lon=Number(a.longitude).toFixed(6);
   const acc=a.gps_accuracy!=null?' (\u00b1'+Math.round(a.gps_accuracy)+' m)':'';
   text+='\n\nMap'+acc+': https://maps.google.com/?q='+lat+','+lon;
  }else text+='\n\nCoordinates are unavailable for this person right now.';
  return text;
 }catch{return null}
}


function observeCompletedWire(wire,session,kind,request){
 if(!session||kind!=='primary')return;
 let finished=false,hasText=false;
 const check=d=>{for(const c of d?.choices||[]){if(c.finish_reason==='stop')finished=true;if(c.message?.content||c.delta?.content)hasText=true;}};
 try{check(JSON.parse(wire))}catch{for(const line of wire.split('\n')){if(!line.startsWith('data: '))continue;try{check(JSON.parse(line.slice(6)))}catch{}}}
 if(finished&&hasText)completeTask(session,true,undefined,{finalComplete:true,toolsUsed:currentTurn(request||{})?.calls.length||0});return finished&&hasText;
}

const ZERO_FOOTER='\n\nUsage (local): 0 tokens \u00b7 certified replay, no inference';
const PORT=Number(process.env.MEDIA_PROXY_PORT||8011);
const metrics={upstream:0,cloud:0,local:0,templateHits:0,formattedResults:0,titles:0};
const activeControls=new Map();
const server=http.createServer(async(req,res)=>{
 if(req.url==='/discard-session'&&req.method==='POST'){
  if(!process.env.VLLM_API_KEY||req.headers.authorization!=='Bearer '+process.env.VLLM_API_KEY){res.writeHead(401);res.end();return;}
  let raw='';for await(const chunk of req){raw+=chunk;if(raw.length>512){res.writeHead(413);res.end();return;}}
  let id;try{id=JSON.parse(raw).sessionID}catch{}
  if(typeof id!=='string'||!/^ses_[a-zA-Z0-9_-]+$/.test(id)){res.writeHead(400);res.end();return;}
  for(const ctl of activeControls.get(id)||[])ctl.abort(new Error('Rejected session discarded'));
  activeControls.delete(id);forgetCloudSession(id);clearEvidenceMemo();res.end('discarded');return;
 }
 if(req.url==='/health'){res.end('ok');return;}
 if(req.url==='/metrics'&&req.method==='GET'){res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify(metrics));return;}
 const genericAgent=req.url==='/generic-agent/v1/chat/completions';
 const genericCloud=req.url==='/generic-cloud/v1/chat/completions';
 const generic=genericAgent||genericCloud;
 const cloud=genericCloud||req.url==='/cloud/v1/chat/completions';
 if(req.method!=='POST'||(!generic&&!cloud&&req.url!=='/local/v1/chat/completions')){res.writeHead(404);res.end();return;}
 if(req.headers['x-media-budget-exhausted']==='true'){res.writeHead(504,{'content-type':'application/json'});res.end(JSON.stringify({error:{message:'Media model-step budget exceeded',type:'media_step_budget'}}));return;}
 const control=new AbortController();
 const max=generic?900000:cloud?120000:90000;
 const budget=Math.max(1,Math.min(max,Number(req.headers['x-media-timeout-ms'])||max));
 const timer=setTimeout(()=>control.abort(new Error('deadline')),budget);
 let processingRef=null;
 let cloudCall=null,cloudStatus=null,cloudOutcome='incomplete',cloudModelFinished=false;
 const session=req.headers['x-media-session']||req.headers['x-procedure-session'];
 if(session&&isDiscarded(session)){clearTimeout(timer);res.writeHead(410,{'content-type':'application/json'});res.end(JSON.stringify({error:{type:'discarded_session',message:'This rejected session was discarded. Start a fresh session.'}}));return;}
 if(session){if(!activeControls.has(session))activeControls.set(session,new Set());activeControls.get(session).add(control);}
 res.on('close',()=>{if(!res.writableEnded)control.abort(new Error('client disconnected'))});
 try{
  let bytes=0;const chunks=[];
  for await(const chunk of req){bytes+=chunk.length;if(bytes>40*1024*1024)throw new Error('request too large');chunks.push(chunk);}
  const headers={'content-type':'application/json'};
  if(req.headers.authorization)headers.authorization=req.headers.authorization;
  if(!cloud)headers.authorization='Bearer '+process.env.VLLM_API_KEY;
  const incoming=JSON.parse(Buffer.concat(chunks).toString());
  const ha=req.headers['x-request-kind']==='ha'||(!cloud&&!generic&&['qwen38-27b','qwen35-9b'].includes(incoming.model));
  const kind=req.headers['x-ha-request-kind']||req.headers['x-procedure-request-kind']||'primary';
  let userQuery;try{userQuery=decodeURIComponent(req.headers['x-ha-request-task']||req.headers['x-procedure-request-task']||'')}catch{}
  if((ha||generic)&&/title/i.test(kind)&&userQuery){
   const task=/password|token|secret|bearer|eyJ\w{10}/i.test(userQuery)?'OpenCode task':userQuery;
   const text=task.trim().split(/\s+/).slice(0,10).join(' ').slice(0,100)||'OpenCode task';
   metrics.titles++;
   const wire=reportWire(incoming,text);res.writeHead(200,{'content-type':wire.type});res.end(wire.body);
   console.log(JSON.stringify({at:new Date().toISOString(),route:'procedure-title-renderer',status:200,zeroLLM:true,session}));return;
  }
  if(ha&&kind==='primary'&&req.headers['x-ha-needs-target']==='true'){
   const wire=reportWire(incoming,'Which device or devices do you mean?\n\nUsage (local): 0 tokens · clarification needed, no inference');res.writeHead(200,{'content-type':wire.type});res.end(wire.body);return;
  }
  // "where is <person>" is answered in code, with a Google Maps link.
  if(!cloud&&!generic&&kind==='primary'&&userQuery){
   const located=await personLocationAnswer(userQuery);
   if(located){
    const wire=reportWire(incoming,located+'\n\nUsage (local): 0 tokens \u00b7 deterministic lookup, no inference');
    res.writeHead(200,{'content-type':wire.type});res.end(wire.body);
    console.log(JSON.stringify({at:new Date().toISOString(),route:'person-location',status:200,zeroLLM:true,session}));return;
   }
  }
  if(ha&&kind==='primary'&&userQuery&&!currentTurn(incoming,userQuery)?.calls.length){
   const users=(incoming.messages||[]).filter(m=>m.role==='user');
   const routine=await executeNamedRoutine(userQuery,{session:session||'',turn:String(users.length)+':'+JSON.stringify(users.at(-1)||{}).slice(-500)});
   if(routine){const wire=reportWire(incoming,routine.text+'\n\nUsage (local): 0 tokens · HA routine invocation, no inference');res.writeHead(200,{'content-type':wire.type});res.end(wire.body);console.log(JSON.stringify({at:new Date().toISOString(),route:'ha-named-routine',session,status:200,ok:routine.ok,uncertain:routine.uncertain,entity_id:routine.entity_id}));return;}
  }
  const machineFormat=/\b(json|csv|xml|yaml)\b|\b(?:number|value|answer)\s+only\b|\bonly\s+(?:a\s+)?(?:number|value|answer)\b/i.test(userQuery||'');
  // Auxiliary requests (including compaction) must never replay user actions.
  if((ha||generic)&&kind==='primary'&&!machineFormat&&!(cloud&&cloudDirective(userQuery||'')&&!currentTurn(incoming,userQuery)?.calls.length)){
   let direct=null;
   try{direct=await tryExecutionTemplate(incoming,{userQuery});if(!direct)direct=await learnExecutionTemplate(incoming,{userQuery,sessionID:session,run:request=>runProcedure(request,{timeoutMs:2000})})}catch(error){console.log(JSON.stringify({at:new Date().toISOString(),route:'template-fallback',error:error?.name||'Error'}))}
   if(!direct&&generic&&userQuery&&!currentTurn(incoming,userQuery)?.calls.length){const calc=await tryCalculation(userQuery);if(calc&&!isDiscarded(session)){saveTemplate(userQuery,calc.recipe);direct={text:calc.text,source:'verified-local-calculation',zeroLLM:true};}}
   if(direct){
    if(direct.source==='verified-local-calculation')metrics.calculations=(metrics.calculations||0)+1;else if(direct.zeroLLM)metrics.templateHits++;else metrics.formattedResults++;
    const wire=reportWire(incoming,kind==='primary'&&direct.zeroLLM?direct.text+(direct.source==='verified-local-calculation'?'\n\nUsage (local): 0 tokens · deterministic calculation, no inference':ZERO_FOOTER):direct.text);res.writeHead(200,{'content-type':wire.type});res.end(wire.body);
    console.log(JSON.stringify({at:new Date().toISOString(),route:direct.source,status:200,zeroLLM:direct.zeroLLM,session,chars:direct.text.length}));return;
   }
  }
  const report=ha&&kind==='primary'&&!machineFormat&&isSimpleStatusQuery(userQuery)?(reportFromRequest(incoming)||formatNativeStatus(incoming,userQuery)):null;
  if(report!==null){
   const wire=reportWire(incoming,report);res.writeHead(200,{'content-type':wire.type});res.end(wire.body);
   console.log(JSON.stringify({at:new Date().toISOString(),route:'ha-report-renderer',status:200,session,chars:report.length}));return;
  }
  const agent=ha||genericAgent;
  // Shared provider boundary: every frontend and both model tiers get the same
  // completed-task cleanup and bounded active evidence before any inference.
  const hygienic=await sanitizeContext(incoming,{signal:control.signal,session,vision:!cloud&&!agent});
  const optimized=cloud?await optimizeCloudRequest(hygienic.body,{signal:control.signal,session}):hygienic.body;
  let capture=false;try{capture=JSON.parse(fsmod.readFileSync('/home/somdutta/.local/state/opencode/completion-check/trace-sessions.json','utf8')).sessions?.includes(session)}catch{}
  const snapshot=cloud||capture?snapshotCloudRequest(incoming,optimized,{session,kind}):null;
  const payload=JSON.stringify(cloud?optimized:{...optimized,model:agent?'qwen36-agent':'qwen35-vision'});
  const target=cloud?'https://openrouter.ai/api/v1/chat/completions':agent?(process.env.OPENCODE_TEST_AGENT_ENDPOINT||'http://127.0.0.1:8000/v1/chat/completions'):'http://127.0.0.1:8001/v1/chat/completions';
  metrics.upstream++;if(cloud)metrics.cloud++;else metrics.local++;
  if(cloud){cloudCall={callID:randomUUID(),sessionID:session,model:incoming.model,requestKind:kind,task:userQuery,startedAt:Date.now()};recordCloudCall({...cloudCall,event:'started'});}
  processingRef=beginProcessing({session,provider:cloud?'remote':'local',model:cloud?incoming.model:agent?'qwen36-agent':'qwen35-vision',inputTokens:hygienic.stats.inputTokens,inputTokenKind:!cloud&&!agent?'text-only':'text',kind});
  const upstream=await fetch(target,{method:'POST',headers,body:payload,signal:control.signal});
  cloudStatus=upstream.status;cloudOutcome=upstream.ok?'headers-received':'http-error';
  {
   // Validate a final answer before publishing it. Native tool continuations
   // preserve the existing request and receipts; no user prompt is resubmitted.
   let result=await upstream.text();if(snapshot)snapshotCloudResponse(snapshot,result,upstream.status);if(res.destroyed)return;
   if(upstream.ok&&kind==='primary'&&(cloud||agent)&&session){
    const summary=wireSummary(result);
    const problem=summary.finished&&!summary.toolCalls?completionProblem(optimized,summary.answer):null;
    if(problem){
     const repair=noteCompletionFailure(session,currentRequest(optimized),problem,cloud?'cloud':'local');
     if(repair.attempts<=2&&optimized.tools?.some(t=>t.function?.name==='discover_capabilities')){
      result=discoveryContinuation(result,optimized.model);
      console.log(JSON.stringify({at:new Date().toISOString(),route:'completion-recovery',session,reason:problem,attempt:repair.attempts,next:repair.route||'discovery'}));
     }else{
      res.writeHead(422,{'content-type':'application/json'});res.end(JSON.stringify({error:{type:'incomplete_response',message:'The model did not complete the request after bounded recovery. No successful completion was recorded; completed actions were not replayed.'}}));return;
     }
    }
   }
   // Local answers carry their own token footer, so the cloud model never has to
   // report local usage. Handles both JSON and SSE responses; only for a final
   // answer (no tool calls pending).
   if(!cloud&&!generic&&upstream.status===200&&kind==='primary'&&!machineFormat){
    try{result=withLocalFooter(result,upstream.headers.get('content-type')||'');metrics.localFooters=(metrics.localFooters||0)+1}catch(error){console.log(JSON.stringify({at:new Date().toISOString(),route:'local-footer-error',error:String(error.message||error).slice(0,120)}))}
   }
   if(upstream.status===200)cloudModelFinished=!!observeCompletedWire(result,session,kind,incoming);cloudOutcome=upstream.ok?'response-complete':'http-error';res.writeHead(upstream.status,{'content-type':upstream.headers.get('content-type')||'application/json'});res.end(result);
  }
  console.log(JSON.stringify({at:new Date().toISOString(),route:generic?(cloud?'generic-cloud':'generic-agent'):(cloud?'cloud':'local'),status:upstream.status,session,bytes,requestKind:kind}));
 }catch(error){
  cloudOutcome=control.signal.aborted?'timeout-or-disconnect':'transport-error';
  if(!res.destroyed){
   if(res.headersSent)res.end();
   else{res.writeHead(error instanceof ContextLimitError?413:control.signal.aborted?504:502,{'content-type':'application/json'});res.end(JSON.stringify({error:{message:error instanceof ContextLimitError?error.message:control.signal.aborted?'Processing deadline exceeded':'Upstream request failed',type:error instanceof ContextLimitError?'context_safety_limit':'budget_or_upstream'}}));}
  }
  console.log(JSON.stringify({at:new Date().toISOString(),route:generic?'generic-error':cloud?'cloud':'local',status:error instanceof ContextLimitError?413:control.signal.aborted?504:502,session}));
 }finally{endProcessing(processingRef);if(session){activeControls.get(session)?.delete(control);if(!activeControls.get(session)?.size)activeControls.delete(session);}if(cloudCall)recordCloudCall({...cloudCall,event:'finished',status:cloudStatus,outcome:res.destroyed&&!res.writableEnded?'client-disconnect':cloudOutcome,modelReplyComplete:cloudModelFinished,elapsedMs:Date.now()-cloudCall.startedAt});clearTimeout(timer);}
});
server.requestTimeout=150000;
server.listen(PORT,'127.0.0.1',()=>console.log(`Procedure/media gateway listening on loopback:${PORT}`));
