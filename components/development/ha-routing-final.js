import {procedureHint} from '../../lib/procedure-memory.mjs';
import {isStatusReport,REPORT_TOOL} from '../../lib/ha-reports.mjs';
import {installMediaRouter} from './media-routing.js';
import { appendFileSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import {findLearned,candidateFromSuccess,remember,disableLearned} from './learning.js';
const LOCAL={providerID:'evo-agent',id:'qwen36-agent'};
const CLOUD={providerID:'openrouter',id:'deepseek/deepseek-v4.1-flash-1017'};
export const HA_LOCAL_MS=60000;
const routingMeta=s=>/\b(router|routing|openrouter)\b/.test(s)&&/^(?:please )?(?:explain|describe|how|what|which|tell me|do you know|are you aware|can you explain)\b/.test(s);
const coding=s=>/\b(write|implement|debug|develop|refactor|configure|install)\b.{0,45}\b(code|script|plugin|integration|server|config|automation)\b/.test(s);
const history=s=>/\b(visit\w*|locations?|where)\b/.test(s)&&/\b(today|yesterday|visited|history|locations|been|went)\b/.test(s)&&!/\b(stock|news|flight|ticket|vacation|holiday)\b/.test(s);
const devices=s=>/\b(light\w*|dimmer\w*|fan\w*|thermostat|curtain\w*|blind\w*|den switch)\b/.test(s)&&/\b(on|off|state|status|dim|bright\w*|set|turn|switch|are|is)\b/.test(s);
export function isMixedRequest(text){
 const s=text.toLowerCase();if(coding(s)||routingMeta(s))return false;
 const media=/\b(video|footage|clip|ring|door\s?bell|camera|recording)\b/.test(s);
 return (devices(s)&&/\b(?:and|then|also)\s+(?:then\s+)?(?:turn|switch|set|run|show|share|analy[sz]e|provide|list|check)\b/.test(s)) || (history(s)&&devices(s)) || (media&&(history(s)||devices(s)||/\b(home assistant|homeassistant|ha mcp)\b/.test(s)));
}
export function classify(text){
 const s=text.toLowerCase();if(coding(s)||routingMeta(s)||isMixedRequest(s))return null;
 if(history(s))return 'history';
 if(isStatusReport(text))return 'devices';
 if(/\b(home assistant|homeassistant|ha mcp)\b/.test(s)||devices(s))return 'devices';
 return null;
}
const isMcp=name=>/^(home[-_]assistant_|ha[-_]history_)/.test(name);
const allow=(name,kind)=>kind==='history'?/^ha[-_]history_/.test(name)||/GetDateTime$/.test(name):isMcp(name);
const isLocal=state=>state&&['history','devices'].includes(state.kind);
const key=id=>'ha-turn:'+id;
export const isHAFollowup=text=>/^(?:please )?(?:(?:turn|switch|set|dim|make) (?:it|them|those)|(?:who|what|when|why|how)\b.{0,60}\b(?:it|them|those|they)\b|(?:and |what about )?(?:on|off|brighter|dimmer)\b|what about (?:yesterday|today)\b)/i.test(text);
const canonical=value=>JSON.stringify(value,(_k,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.entries(v).sort(([a],[b])=>a.localeCompare(b))):v);
export default {
 id:'ha-mcp-routing',
 async setup(ctx){
  const media=await installMediaRouter(ctx);
  const turns=new Map();
  const learningPath=ctx.options?.learningStore || homedir()+'/.local/share/opencode/ha-router/learned-routes.json';
  const stateFor=async id=>turns.get(id)||await ctx.storage?.get(key(id));
  const save=async(id,state)=>{turns.set(id,state);await ctx.storage?.set(key(id),JSON.parse(JSON.stringify(state)));};
  const log=obj=>{try{appendFileSync(homedir()+'/ha-local-debug/routing.jsonl',JSON.stringify({at:new Date().toISOString(),...obj})+'\n')}catch{}};
  const fallback=async(id,state,reason)=>{
   if(state.learnedRouteId){try{await disableLearned(learningPath,state.learnedRouteId,reason);}catch(error){log({event:'learning-error',reason:String(error.message||error)});}}
   state.kind='fallback';state.reason=reason;state.fulfilled=true;delete state.requiredTool;
   await save(id,state);await ctx.session.switchModel({sessionID:id,model:CLOUD});
   log({sessionID:id,event:'fallback',reason,model:CLOUD});
  };
  await ctx.session.hook('prompt',async event=>{
   const promptStartedAt=Date.now();
   const text=(event.prompt.text||'').trim().replace(/^["']|["']$/g,'');
   const prior=await stateFor(event.sessionID);
   if(await media.prompt(event)){
    turns.delete(event.sessionID);await ctx.storage?.remove(key(event.sessionID));return;
   }
   const seeded=isHAFollowup(text)?(await ctx.session.get({sessionID:event.sessionID})).metadata?.haContextKind:null;
   const mixed=isMixedRequest(text);
   const baseKind=classify(text);
   const learned=!mixed&&!baseKind&&!coding(text.toLowerCase())?findLearned(learningPath,text):null;
   const kind=mixed?'orchestrate':baseKind||learned?.route.kind||(['devices','history'].includes(seeded)?seeded:null)||(isLocal(prior)&&isHAFollowup(text)?prior.kind:null);
   if(kind==='orchestrate'){
    const session=await ctx.session.get({sessionID:event.sessionID});
    const child=session.agent==='ha';
    await save(event.sessionID,{kind:child?'fallback':kind,reason:child?'A mixed task must not be delegated intact':undefined,previous:prior?.previous||CLOUD,startedAt:Date.now(),calls:0,failures:0});
    await ctx.session.switchModel({sessionID:event.sessionID,model:CLOUD});
    log({sessionID:event.sessionID,event:'orchestrate',model:CLOUD});return;
   }
   if(kind){
    const reportOnly=kind==='devices'&&isStatusReport(text);
    if(ctx.tool?.list){
     let ready=false;
     for(let attempt=0;attempt<40;attempt++){
      const catalog=await ctx.tool.list();
      const statusOnly=kind==='devices'&&!/\b(all|every|everything|turn|toggle|set|dim|change|enable|disable|why|cause|history|when|automation|script|also)\b/i.test(text)&&/\b(status|state|is|are)\b/i.test(text)&&/\b(light|lights|fan|fans|switch|switches)\b/i.test(text);
      const requiredReady=reportOnly?catalog.some(tool=>tool.id===REPORT_TOOL):kind==='devices'&&!statusOnly?catalog.some(tool=>/^home[-_]assistant_/.test(tool.id)):catalog.some(tool=>allow(tool.id,kind));
      if(requiredReady && (!learned || catalog.some(tool=>tool.id===learned.route.requiredTool))){ready=true;break;}
      if(attempt===0&&ctx.tool.reload)await ctx.tool.reload();
      await new Promise(resolve=>setTimeout(resolve,250));
     }
     if(!ready){await fallback(event.sessionID,{previous:CLOUD,learnedRouteId:learned?.route.id},learned?'Learned route tool is unavailable':'HA MCP catalog unavailable');return;}
    }
    const session=await ctx.session.get({sessionID:event.sessionID});
    const state={kind,previous:prior?.previous||session.model,broad:/\b(all|every|everything)\b/i.test(text),target:/\bden\b/i.test(text)?'Den Switch':(!classify(text)?prior?.target:undefined),fulfilled:false,startedAt:promptStartedAt,calls:0,failures:0,failureCounts:{}};
    state.fastStatus=kind==='devices'&&!mixed&&/\b(status|state|is|are)\b/i.test(text)&&/\b(light|lights|fan|fans|switch|switches)\b/i.test(text)&&!state.broad&&!/\b(turn|toggle|set|dim|change|enable|disable|why|cause|history|when|automation|script|and then|also)\b/i.test(text);
    state.requestText=text;state.reportOnly=reportOnly;
    if(kind==='history')state.requiredTool='ha-history_get_visited_locations';
    else if(state.target==='Den Switch')state.requiredTool=/^(?:please )?(?:turn|switch|set)\b|^(?:on|off)\b/i.test(text)?'home-assistant_intent__HassTurn'+(/\boff\b/i.test(text)?'Off':'On'):'home-assistant_homeassistant__GetLiveContext';
    if(learned){
     state.learnedRouteId=learned.route.id;state.learnedIntent=learned.route.task;
     state.requiredTool=learned.route.requiredTool;state.target=learned.route.target || state.target;
    }
    if(state.fastStatus)state.requiredTool='ha-history_get_device_status';
    if(state.reportOnly)state.requiredTool=REPORT_TOOL;
    await save(event.sessionID,state);await ctx.session.switchModel({sessionID:event.sessionID,model:LOCAL});
    log({sessionID:event.sessionID,event:learned?'learned-route':'route',kind,model:LOCAL,learnedRouteId:learned?.route.id,score:learned?.score});
   }else{
    turns.delete(event.sessionID);await ctx.storage?.remove(key(event.sessionID));
    if(prior?.previous)await ctx.session.switchModel({sessionID:event.sessionID,model:prior.previous});
   }
   if(turns.size>1000)turns.delete(turns.keys().next().value);
  });
  await ctx.session.hook('context',async event=>{
   if(await media.active(event.sessionID))return;
   let state=await stateFor(event.sessionID);
   if(!state){
    const session=await ctx.session.get({sessionID:event.sessionID});
    if(session.agent==='ha'){
     state={kind:'devices',previous:CLOUD,calls:0,failures:0,failureCounts:{},startedAt:Date.now(),fulfilled:false};
     await save(event.sessionID,state);
    }
   }
   if(!state)return;
   if(['orchestrate','fallback'].includes(state.kind)){
    state.cloudCalls=(state.cloudCalls||0)+1;await save(event.sessionID,state);
    if(state.cloudCalls>10)throw new Error('DeepSeek coordination reached its step limit; report unresolved tasks instead of looping.');
   }
   if(state.kind==='orchestrate'){
    event.system.push({type:'text',text:'This is a mixed request. You are the DeepSeek coordinator. Break it into individual tasks. Delegate each atomic supported Home Assistant device task and each location-history task separately to the ha subagent; never delegate the complete mixed request. Keep media retrieval/sharing and final synthesis here. Use an explicitly available Ring/video tool for retrieval and an available media delivery tool for sharing; if absent, state that limitation. Never invent a clip, URL, successful action, tool, or unrecorded visited/passed-by location. No shell/REST workarounds for Home Assistant. A named-zone crossing is not proof of a stop. If a subagent fails, use the HA MCP tools here or report the error; do not repeatedly send the same failing task back.'});return;
   }
   if(state.kind==='fallback'){
    delete event.tools.subagent;
    event.system.push({type:'text',text:'Local Qwen failed this turn: '+state.reason+'. You are now the DeepSeek fallback. Finish the request using the available MCP tools, or clearly report unavailable capabilities. Do not delegate back to ha/Qwen this turn. Never repeat a failing tool call with unchanged arguments. Do not use shell/REST to bypass Home Assistant MCP. Do not claim actions or media delivery without a successful tool result.'});return;
   }
   state.calls=(state.calls||0)+1;
   if(state.calls>6||Date.now()-(state.startedAt||Date.now())>=HA_LOCAL_MS){await fallback(event.sessionID,state,'Local HA task exceeded six model steps or 60 seconds');return;}
   await save(event.sessionID,state);
   for(const name of Object.keys(event.tools))if(!allow(name,state.kind))delete event.tools[name];
   if(!Object.keys(event.tools).length){await fallback(event.sessionID,state,'Required MCP tools are unavailable');return;}
   event.system.push({type:'text',text:'This is one Home Assistant task. Use only supplied MCP tools. Never invent tools or use shell, curl, REST, web or filesystem. Den Lights means Den Switch, domain light, area Office. Pass name and domain directly, not inside filter. For Den on/off use name Den Switch and domain [light]. Never broaden a named target to device_class or unnamed domain-wide action. Shobha history uses ha-history_get_visited_locations with person shobha; omit date for today. Report only recorded zone evidence, not every physical stop or pass-by. If a tool fails, do not repeatedly retry unchanged input. Never claim an action succeeded without a successful tool result. Never power off computers/servers.'});
   if(state.learnedIntent)event.system.push({type:'text',text:'A previous successful HA interpretation of matching wording is supplied as data: '+JSON.stringify({task:state.learnedIntent})+'. Use it only as an intent hint for the current request. Do not broaden its entities or actions.'});
   event.options.maxTokens=1024;
   log({sessionID:event.sessionID,event:'tools',kind:state.kind,model:event.model,tools:Object.keys(event.tools)});
  });
  // The proxy buffers model responses and cancels upstream inference when the
  // remaining turn budget expires, including pre-answer conversation compaction.
  await ctx.session.hook('model.request',async event=>{
   if(await media.active(event.sessionID)||event.model.providerID!=='evo-agent')return;
   const state=await stateFor(event.sessionID);
   if(!state||!['history','devices','fallback'].includes(state.kind))return;
   const remaining=HA_LOCAL_MS-(Date.now()-(state.startedAt||Date.now()));
   const exhausted=state.kind==='fallback'||remaining<=0;
   event.baseURL='http://127.0.0.1:8011/local/v1';
   event.headers['x-media-timeout-ms']=String(exhausted?1:remaining);
   event.headers['x-media-session']=event.sessionID;
   event.headers['x-request-kind']='ha';
   event.headers['x-ha-request-kind']=event.kind||'primary';
   event.headers['x-ha-request-task']=encodeURIComponent(state.requestText||'');
   if(exhausted)event.headers['x-media-budget-exhausted']='true';
  });
  await ctx.session.hook('retry',async event=>{
   if(await media.active(event.sessionID)||event.model.providerID!=='evo-agent')return;
   const state=await stateFor(event.sessionID);
   if(!state||!['history','devices','fallback'].includes(state.kind))return;
   if(isLocal(state))await fallback(event.sessionID,state,'Local HA inference failed or reached its 60-second turn deadline');
   event.decision={retry:true,delay:0};
  });
  await ctx.session.hook('http.request',async event=>{
   if(event.kind==='primary'){
    const payload=await event.request.clone().json();
    const imagePart=part=>['image_url','image','input_image'].includes(part.type);
    const users=(payload.messages||[]).filter(m=>m.role==='user'&&Array.isArray(m.content)&&m.content.some(imagePart));
    let changed=false;
    for(const m of users.slice(0,-1)){
     m.content=m.content.filter(part=>!imagePart(part));
     if(!m.content.length)m.content=[{type:'text',text:'[Earlier image omitted; retain the prior visual analysis as context.]'}];
     changed=true;
    }
    if(changed)event.request=new Request(event.request,{body:JSON.stringify(payload)});
   }
   if(event.model.providerID!=='evo-agent')return;
   const state=await stateFor(event.sessionID);if(!isLocal(state))return;
   const body=await event.request.clone().json();
   if(event.kind!=='primary'){
    body.chat_template_kwargs={...body.chat_template_kwargs,enable_thinking:false};
    body.max_tokens=Math.min(body.max_tokens||1024,/title/i.test(event.kind)?128:1024);
    event.request=new Request(event.request,{body:JSON.stringify(body)});return;
   }
   {
    if(state.reportOnly)body.tools=(body.tools||[]).filter(t=>t.function?.name===REPORT_TOOL);
    else if(state.fastStatus)body.tools=(body.tools||[]).filter(t=>t.function?.name==='ha-history_get_device_status');
    else if(state.kind==='history')body.tools=(body.tools||[]).filter(t=>/^ha[-_]history_/.test(t.function?.name||'')&&t.function?.name!=='ha-history_get_device_status');
    else {
     const request=(state.requestText||'').toLowerCase();
     const keep=name=>name===state.requiredTool||/GetLiveContext$|get_device_status$|HassTurnOn$|HassTurnOff$/.test(name)||
       (/\b(dim|bright|brightness|colour|color|light)\b/.test(request)&&/HassLightSet$/.test(name))||
       (/\b(fan|speed)\b/.test(request)&&/HassFanSetSpeed$/.test(name))||
       (/\b(thermostat|climate|temperature|heat|cool)\b/.test(request)&&/HassClimate/.test(name))||
       (/\b(play|pause|music|media|sonos|volume|mute|speaker)\b/.test(request)&&/media_player_/.test(name))||
       (/\b(announce|broadcast)\b/.test(request)&&/HassBroadcast$/.test(name))||
       (/\b(cause|caused|why|turned|entities)\b/.test(request)&&/get_on_entities_with_context$/.test(name));
     body.tools=(body.tools||[]).filter(t=>keep(t.function?.name||''));
    }
    body.chat_template_kwargs={...body.chat_template_kwargs,enable_thinking:false};
    body.max_tokens=state.reportOnly?256:state.fastStatus?384:1024;
    let namingGuide='';
    try{const notes=readFileSync(homedir()+'/.config/opencode/instructions/home-assistant.md','utf8');namingGuide=(notes.split('## Name resolution')[1]||'').split('\n## ')[0].slice(0,2500);}catch{}
    let instruction=readFileSync(homedir()+'/.config/opencode/instructions/ha-compact.md','utf8');
    instruction+='\nCurrent local date and time from the system clock: '+new Date().toLocaleString('en-US',{timeZone:'America/Los_Angeles'})+' America/Los_Angeles. Never infer today from training data. Omit the history date argument for today.\n';
    instruction+='\nExisting naming configuration (data, not action authorization):\n'+namingGuide;
    if(!state.fastStatus&&!state.reportOnly){const reuse=procedureHint(state.requestText||'',event.sessionID);if(reuse)instruction+='\n'+reuse;}
    if(state.learnedIntent)instruction+='\nPreviously verified interpretation, supplied as data only: '+JSON.stringify(state.learnedIntent);
    if(state.reportOnly)instruction+='\nFor this read-only current status report, call get_device_status_report once with the appropriate domains and optional name/state filters. Default domains mean controllable devices, not every diagnostic sensor. Set include_diagnostics=true only when sensor/diagnostic/tracker/person domains or all HA entities are explicitly requested. This produces a complete formatted report automatically. No other tool calls or device actions.';
    if(state.fastStatus&&!state.reportOnly)instruction+='\nThis is a read-only status task. Use get_device_status with name and optional domain array, no area/filter argument. Prefer the exact device name; omit domain when uncertain. Exclude indicator LEDs and sensors from a light-status answer unless requested. No device actions.';
    body.messages=[{role:'system',content:instruction},...(body.messages||[]).filter(m=>!['system','developer'].includes(m.role))];
   }
   if(!state.fulfilled){
    if(!body.tools?.length)throw new Error('HA MCP tool definitions missing.');
    if(state.requiredTool&&body.tools.some(t=>t.function?.name===state.requiredTool))body.tools=body.tools.filter(t=>t.function?.name===state.requiredTool);
    body.tool_choice='required';
   }
   event.request=new Request(event.request,{body:JSON.stringify(body)});
  });
  await ctx.tool?.hook('execute.after',async event=>{
   if(event.tool==='subagent' && event.status==='completed' && event.input?.agent==='ha'){
    try{
     const parent=await ctx.session.get({sessionID:event.sessionID});
     const messages=await ctx.session.context({sessionID:event.sessionID});
     const text=(messages.filter(m=>m.type==='user').at(-1)?.text || '').trim().replace(/^["']|["']$/g,'');
     const childID=event.result?.metadata?.sessionID;
     if(parent.model?.id?.includes('deepseek') && childID && !isMixedRequest(text) && !classify(text) && !coding(text.toLowerCase())){
      const child=await ctx.session.context({sessionID:childID});
      const candidate=candidateFromSuccess({text,task:event.input.prompt,child});
      if(candidate && await remember(learningPath,candidate))log({sessionID:event.sessionID,event:'learned',routeID:candidate.id,kind:candidate.kind});
      else log({sessionID:event.sessionID,event:'learn-skipped',reason:'Delegation did not meet verified MCP/entity requirements'});
     }
    }catch(error){log({sessionID:event.sessionID,event:'learning-error',reason:String(error.message || error)});}
   }
   const state=await stateFor(event.sessionID);if(!isLocal(state))return;
   if(event.status==='completed'&&allow(event.tool,state.kind)){
    state.fulfilled=true;
    const signature=event.tool+':'+canonical(event.input||{});
    state.successCounts||={};state.successCounts[signature]=(state.successCounts[signature]||0)+1;
    if(state.successCounts[signature]>=2){await fallback(event.sessionID,state,'Repeated identical successful lookup without answering');return;}
   }
   else if(event.status==='error'){
    const signature=event.tool+':'+canonical(event.input||{});
    state.failures=(state.failures||0)+1;state.failureCounts||={};
    state.failureCounts[signature]=(state.failureCounts[signature]||0)+1;
    if(state.failureCounts[signature]>=2||state.failures>=3){await fallback(event.sessionID,state,'Repeated tool failures ('+event.tool+')');return;}
   }
   await save(event.sessionID,state);
  });
  await ctx.tool?.hook('execute.before',async event=>{
   const state=await stateFor(event.sessionID);
   if(/HassTurn(?:On|Off)$/.test(event.tool)&&!event.input?.name&&!event.input?.area&&!event.input?.floor&&!state?.target&&!state?.broad)throw new Error('An explicit device name or area is required; an unnamed group action needs explicit authorization.');
   if(!isLocal(state))return;
   if(event.tool==='ha-history_get_visited_locations'){
    const text=state.requestText||'';
    const explicit=/\b\d{4}-\d{2}-\d{2}\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b/i.test(text);
    if(!explicit&&/\btoday\b/i.test(text)&&!/\byesterday\b/i.test(text)){event.input={...event.input};delete event.input.date;}
    else if(!explicit&&/\byesterday\b/i.test(text)&&!/\btoday\b/i.test(text)){
     const parts=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date()).filter(p=>p.type!=='literal').map(p=>[p.type,p.value]));
     const yesterday=new Date(Date.UTC(Number(parts.year),Number(parts.month)-1,Number(parts.day)-1)).toISOString().slice(0,10);
     event.input={...event.input,date:yesterday};
    }
   }
   if(!allow(event.tool,state.kind))throw new Error('This local task must use its supplied HA MCP tools.');
   if(state.target==='Den Switch'&&/HassTurn(?:On|Off)$/.test(event.tool)){
    event.input={...event.input,name:'Den Switch',domain:['light']};delete event.input.device_class;delete event.input.area;delete event.input.floor;
   }
  });
  await ctx.permission.hook('evaluate',async event=>{
   const state=await stateFor(event.sessionID);
   if(isLocal(state)&&!allow(event.action,state.kind)){event.effect='deny';event.message='Local HA tasks must use their supplied MCP tools. Repeated failures fall back to DeepSeek.';}
  });
 }
};
