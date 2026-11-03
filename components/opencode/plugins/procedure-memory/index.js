import {cleanToolEvidence} from '../../lib/evidence-window.mjs';
import {onDiscard} from '../../lib/session-lifecycle.mjs';
import {isDiscarded} from '/home/somdutta/Projects/agent-learning/src/discard.mjs';
import {localContinuationEstimate} from '../../lib/local-progress-budget.mjs';
import {cloudDirective,forbidsTools,isHAConfiguration} from '../../lib/user-scope.mjs';
import {cloudModel,localModel,policyBudget} from '../../lib/routing-policy.mjs';
import {compactWebMessages} from '../../lib/read-context.mjs';
import {classify,isMixedRequest,isHAFollowup} from '../ha-mcp-routing/index.js';
import {inferHAIntent} from '../../lib/ha-intent.mjs';
import {traceTask,recallTask,taskHint,learningEvent,learnCompletedTask,cleanTask} from '../../lib/task-learning.mjs';
import {rememberProcedure,procedureHint,recallProcedures} from '../../lib/procedure-memory.mjs';
export const LOCAL_BUDGET_MS=policyBudget('generalLocalMs',30000);
export default {id:'procedure-memory',async setup(ctx){
 const tasks=new Map(),turns=new Map();
 onDiscard(id=>{clearTimeout(turns.get(id)?.timer);turns.delete(id);tasks.delete(id);});
 const fallback=async(id,turn,reason)=>{if(turn.failed)return;turn.failed=true;clearTimeout(turn.timer);await ctx.session.switchModel({sessionID:id,model:cloudModel()});learningEvent({sessionID:id,event:'local-fallback',reason,elapsedMs:Date.now()-turn.startedAt});};
 const armBudget=(id,turn)=>{
  turn.timer=setTimeout(async()=>{try{
   if(turns.get(id)!==turn||turn.failed)return;
   const session=await ctx.session.get({sessionID:id});
   if(session.time?.idle>=session.time?.busy&&session.time.idle>=turn.startedAt)return;
   await fallback(id,turn,`${LOCAL_BUDGET_MS/1000}-second wall-clock local budget reached; retain any in-flight tool result for cloud continuation`);
  }catch{learningEvent({sessionID:id,event:'budget-watchdog-error'})}},Math.max(1,LOCAL_BUDGET_MS-(Date.now()-turn.startedAt)));
  turn.timer.unref?.();
 };
 await ctx.session.hook('prompt',async event=>{
  const session=await ctx.session.get({sessionID:event.sessionID});const workspace=session.location?.directory||session.directory||process.cwd();
  const text=event.prompt?.text||'';const task={text,workspace,hasFiles:!!event.prompt?.files?.length,startedAt:Number(event.prompt?.metadata?.opencodeStartedAt)||Date.now()};tasks.set(event.sessionID,task);clearTimeout(turns.get(event.sessionID)?.timer);turns.delete(event.sessionID);
  if(tasks.size>1000)tasks.delete(tasks.keys().next().value);
  const plain=text.trim().replace(/^["']|["']$/g,'');
  const semanticKind=!task.hasFiles&&!forbidsTools(plain)?await inferHAIntent(plain):null;
  if(task.hasFiles||!['configuration','investigation'].includes(semanticKind)&&!forbidsTools(plain)&&(classify(plain)||isHAFollowup(plain)&&/^(?:please )?(?:turn|switch)\b/i.test(plain)||!isMixedRequest(plain)&&['devices','history'].includes(semanticKind)))return;
  if(cloudDirective(text)||/^(?:please )?use glm\b/i.test(text.trim()))return;
  const hit=forbidsTools(text)?null:await recallTask(text,workspace);const turn={hit,workspace,previous:session.model,startedAt:task.startedAt,failed:false,failures:new Map()};turns.set(event.sessionID,turn);armBudget(event.sessionID,turn);
  await ctx.session.switchModel({sessionID:event.sessionID,model:localModel()});learningEvent({sessionID:event.sessionID,event:hit?'local-recall':'local-first',match:hit?.match,taskID:hit?.id});
 });
 await ctx.session.hook('model.request',async event=>{
  let task=tasks.get(event.sessionID);
  if(!task){try{const session=await ctx.session.get({sessionID:event.sessionID}),messages=await ctx.session.context({sessionID:event.sessionID}),user=messages.filter(m=>m.type==='user').at(-1);if(user?.text){task={text:user.text,workspace:session.location?.directory||session.directory||process.cwd(),hasFiles:!!user.files?.length,startedAt:Date.now(),recovered:true};tasks.set(event.sessionID,task);}}catch{}}
  if(!task)return;const provider=event.model?.providerID;task.provider=provider;
  if(!event.kind||event.kind==='primary'){try{traceTask(event.sessionID,task.text,task.workspace,provider)}catch{learningEvent({sessionID:event.sessionID,event:'learning-write-error'})}}
  event.headers||={};
  let haTask='';try{haTask=decodeURIComponent(event.headers['x-ha-request-task']||'')}catch{}
  const currentText=task.text.trim().replace(/^["']|["']$/g,'');
  if(event.headers['x-request-kind']==='ha'&&haTask===currentText||task.hasFiles&&event.headers['x-media-session'])return;
  for(const name of ['x-request-kind','x-ha-request-kind','x-ha-request-task','x-ha-needs-target','x-media-session','x-media-budget-exhausted'])delete event.headers[name];
  if(!['openrouter','evo-agent'].includes(provider))return;
  if(provider==='evo-agent'&&!turns.has(event.sessionID)&&!task.hasFiles){const recovered={hit:null,workspace:task.workspace,startedAt:task.startedAt,failed:false,failures:new Map()};turns.set(event.sessionID,recovered);armBudget(event.sessionID,recovered);}
  event.baseURL='http://127.0.0.1:8011/'+(provider==='openrouter'?'generic-cloud':'generic-agent')+'/v1';
  event.headers['x-procedure-request-kind']=event.kind||'primary';event.headers['x-procedure-request-task']=encodeURIComponent(task.text);event.headers['x-procedure-session']=event.sessionID;
  const turn=turns.get(event.sessionID);if(provider==='evo-agent'&&turn&&!turn.failed&&(!event.kind||event.kind==='primary')){turn.modelStartedAt=Date.now();turn.modelStepRecorded=false;}
  if(provider==='evo-agent'&&turn&&!turn.failed)event.headers['x-media-timeout-ms']=String(Math.max(1,LOCAL_BUDGET_MS-(Date.now()-turn.startedAt)));
  else if(provider==='openrouter')event.headers['x-media-timeout-ms']='120000';
  // A session switch does not replace a request already built with the old model.
  // Reject that stale local request; retry resolves the switched cloud model.
  if(provider==='evo-agent'&&turn?.failed){event.headers['x-media-timeout-ms']='1';event.headers['x-media-budget-exhausted']='true';learningEvent({sessionID:event.sessionID,event:'stale-local-request-blocked'});}
 });
 await ctx.session.hook('context',async event=>{
  if(isDiscarded(event.sessionID))throw new Error('This rejected session was discarded. Start a fresh session.');
  const task=tasks.get(event.sessionID);if(!task)return;const turn=turns.get(event.sessionID);
  if(turn&&!turn.failed){const prediction=localContinuationEstimate({...turn,budgetMs:LOCAL_BUDGET_MS});if(prediction.escalate)await fallback(event.sessionID,turn,prediction.estimatedNextMs===null?'Local time budget exhausted':`Next local pass estimated ${Math.round(prediction.estimatedNextMs)}ms with ${Math.round(prediction.remainingMs)}ms remaining; completed tool results retained`);}
  if(forbidsTools(task.text)){for(const name of Object.keys(event.tools||{}))delete event.tools[name];event.system.push({type:'text',text:'The current user request explicitly forbids tool calls. Answer only from provided information or explain what information is missing.'});return;}
  if(turn?.hit)event.system.push({type:'text',text:taskHint(turn.hit,event.sessionID,task.workspace,task.text)});
  const hint=turn?.hit?'':procedureHint(task.text,event.sessionID,task.workspace);if(hint)event.system.push({type:'text',text:hint});
 });
 await ctx.session.hook('http.request',async event=>{
  const turn=turns.get(event.sessionID);if(!turn||turn.failed||!event.request||event.kind&&event.kind!=='primary'||event.request.headers.get('x-request-kind')==='ha')return;
  const body=await event.request.clone().json();body.messages=compactWebMessages(body.messages||[],tasks.get(event.sessionID)?.text||'');body.messages=cleanToolEvidence(body,{task:tasks.get(event.sessionID)?.text||''}).body.messages;body.chat_template_kwargs={...body.chat_template_kwargs,enable_thinking:false};body.max_tokens=Math.min(body.max_tokens||2048,2048);
  // Recalled procedures are advisory. Only current task constraints may remove tools.
  event.request=new Request(event.request,{body:JSON.stringify(body)});
 });
 await ctx.session.hook('retry',async event=>{const turn=turns.get(event.sessionID);if(!turn||event.model?.providerID!=='evo-agent')return;if(!turn.failed)await fallback(event.sessionID,turn,'Local inference failed or exceeded its remaining turn deadline');event.decision={retry:true,delay:0};});
 await ctx.tool?.hook('execute.before',async event=>{if(forbidsTools(tasks.get(event.sessionID)?.text||''))throw new Error('The current user request forbids tool calls.');const turn=turns.get(event.sessionID);if(turn&&!turn.failed&&turn.modelStartedAt&&!turn.modelStepRecorded){turn.lastModelMs=Date.now()-turn.modelStartedAt;turn.modelStepRecorded=true;}if(turn&&!turn.failed&&Date.now()-turn.startedAt>=LOCAL_BUDGET_MS){await fallback(event.sessionID,turn,'Local budget exhausted before next tool call');throw new Error('Local budget exhausted. Continue on the configured cloud model using completed tool results; do not replay completed writes.');}});
 await ctx.tool?.hook('execute.after',async event=>{
  const task=tasks.get(event.sessionID);if(!task)return;const turn=turns.get(event.sessionID);
  if(event.status==='completed'){try{const saved=rememberProcedure({task:cleanTask(task.text),workspace:task.workspace,tool:event.tool,args:event.input||{},result:event.result||{},sessionID:event.sessionID});if(saved)learnCompletedTask({task:task.text,workspace:task.workspace,sessionID:event.sessionID,source:'Successful '+task.provider+' tool step; full task may still need validation'});}catch{}}
  else if(turn&&!turn.failed&&event.status==='error'){const key=event.tool+JSON.stringify(event.input||{}),n=(turn.failures.get(key)||0)+1;turn.failures.set(key,n);if(n>=2)await fallback(event.sessionID,turn,'Repeated identical tool failure');}
  if(turn&&!turn.failed&&Date.now()-turn.startedAt>=LOCAL_BUDGET_MS)await fallback(event.sessionID,turn,`${LOCAL_BUDGET_MS/1000}-second budget reached while a tool was running; completed tool result retained`);
 });
}};
