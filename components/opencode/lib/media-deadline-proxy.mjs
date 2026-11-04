import {beginProcessing,endProcessing} from './processing-trace.mjs';
import {sanitizeContext,ContextLimitError} from './context-hygiene.mjs';
import {isDiscarded} from './discard-session.mjs';
import {snapshotCloudRequest,snapshotCloudResponse} from './cloud-payload-audit.mjs';
import {clearEvidenceMemo} from './evidence-window.mjs';
import {currentTurn} from './execution-templates.mjs';
import {randomUUID} from 'node:crypto';
import {completeTask,recordCloudCall} from './task-learning.mjs';
import {reportWire} from './ha-reports.mjs';
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


function observeCompletedWire(wire,session,kind,request){
 if(!session||kind!=='primary')return;
 let finished=false,hasText=false;
 const check=d=>{for(const c of d?.choices||[]){if(c.finish_reason==='stop')finished=true;if(c.message?.content||c.delta?.content)hasText=true;}};
 try{check(JSON.parse(wire))}catch{for(const line of wire.split('\n')){if(!line.startsWith('data: '))continue;try{check(JSON.parse(line.slice(6)))}catch{}}}
 if(finished&&hasText)completeTask(session,true,undefined,{finalComplete:true,toolsUsed:currentTurn(request||{})?.calls.length||0});return finished&&hasText;
}

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
  activeControls.delete(id);clearEvidenceMemo();res.end('discarded');return;
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
  const machineFormat=/\b(json|csv|xml|yaml)\b|\b(?:number|value|answer)\s+only\b|\bonly\s+(?:a\s+)?(?:number|value|answer)\b/i.test(userQuery||'');
  const agent=ha||genericAgent;
  // Shared provider boundary: every frontend and both model tiers get the same
  // completed-task cleanup and bounded active evidence before any inference.
  const hygienic=await sanitizeContext(incoming,{signal:control.signal,session,vision:!cloud&&!agent});
  const optimized=hygienic.body;
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
