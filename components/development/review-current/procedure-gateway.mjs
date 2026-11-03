import {tryExecutionTemplate,learnExecutionTemplate} from './execution-templates.mjs';
import {reportFromRequest,reportWire} from './ha-reports.mjs';
import http from 'node:http';
import {once} from 'node:events';
const PORT=Number(process.env.MEDIA_PROXY_PORT||8011);
const metrics={upstream:0,cloud:0,local:0,templateHits:0,formattedResults:0,titles:0};
const server=http.createServer(async(req,res)=>{
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
 const session=req.headers['x-media-session']||req.headers['x-procedure-session'];
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
  // Auxiliary requests (including compaction) must never replay user actions.
  if((ha||generic)&&kind==='primary'){
   let direct=null;
   try{direct=await tryExecutionTemplate(incoming,{userQuery});if(!direct)direct=await learnExecutionTemplate(incoming,{userQuery})}catch(error){console.log(JSON.stringify({at:new Date().toISOString(),route:'template-fallback',error:error?.name||'Error'}))}
   if(direct){
    if(direct.zeroLLM)metrics.templateHits++;else metrics.formattedResults++;
    const wire=reportWire(incoming,direct.text);res.writeHead(200,{'content-type':wire.type});res.end(wire.body);
    console.log(JSON.stringify({at:new Date().toISOString(),route:direct.source,status:200,zeroLLM:direct.zeroLLM,session,chars:direct.text.length}));return;
   }
  }
  const report=ha&&!cloud&&kind==='primary'?reportFromRequest(incoming):null;
  if(report!==null){
   const wire=reportWire(incoming,report);res.writeHead(200,{'content-type':wire.type});res.end(wire.body);
   console.log(JSON.stringify({at:new Date().toISOString(),route:'ha-report-renderer',status:200,session,chars:report.length}));return;
  }
  const agent=ha||genericAgent;
  const payload=cloud?Buffer.concat(chunks):JSON.stringify({...incoming,model:agent?'qwen36-agent':'qwen35-vision'});
  const target=cloud?'https://openrouter.ai/api/v1/chat/completions':`http://127.0.0.1:${agent?8000:8001}/v1/chat/completions`;
  metrics.upstream++;if(cloud)metrics.cloud++;else metrics.local++;
  const upstream=await fetch(target,{method:'POST',headers,body:payload,signal:control.signal});
  if(generic){
   // Preserve normal token streaming for general tasks that miss the cache.
   if(res.destroyed)return;
   res.writeHead(upstream.status,{'content-type':upstream.headers.get('content-type')||'application/json'});
   for await(const chunk of upstream.body){if(res.destroyed)break;if(!res.write(Buffer.from(chunk)))await once(res,'drain');}
   if(!res.destroyed)res.end();
  }else{
   // Buffer bounded HA/media calls for clean deadline fallback.
   const result=await upstream.text();if(res.destroyed)return;
   res.writeHead(upstream.status,{'content-type':upstream.headers.get('content-type')||'application/json'});res.end(result);
  }
  console.log(JSON.stringify({at:new Date().toISOString(),route:generic?(cloud?'generic-cloud':'generic-agent'):(cloud?'cloud':'local'),status:upstream.status,session,bytes,requestKind:kind}));
 }catch(error){
  if(!res.destroyed){
   if(res.headersSent)res.end();
   else{res.writeHead(control.signal.aborted?504:502,{'content-type':'application/json'});res.end(JSON.stringify({error:{message:control.signal.aborted?'Processing deadline exceeded':'Upstream request failed',type:'budget_or_upstream'}}));}
  }
  console.log(JSON.stringify({at:new Date().toISOString(),route:generic?'generic-error':cloud?'cloud':'local',status:control.signal.aborted?504:502,session}));
 }finally{clearTimeout(timer);}
});
server.requestTimeout=150000;
server.listen(PORT,'127.0.0.1',()=>console.log(`Procedure/media gateway listening on loopback:${PORT}`));
