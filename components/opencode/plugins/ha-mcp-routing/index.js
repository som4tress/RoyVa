import {resolveReportScope,namedStatusTarget} from '../../lib/ha-scope.mjs';
import {captureTools,restoreSelected,expandedCapabilities,isDiscoveryTool,isGeneralInformationTool,selectCapabilities,DISCOVERY_RULE} from '../../lib/capability-discovery.mjs';
import {onDiscard} from '../../lib/session-lifecycle.mjs';
import {isDiscarded} from '/home/somdutta/Projects/agent-learning/src/discard.mjs';
import {isSimpleStatusQuery} from '../../lib/ha-native-status.mjs';
import {cloudDirective,forbidsTools,isHAConfiguration,isTechnicalRequest,withoutCloudDirective} from '../../lib/user-scope.mjs';
import {cloudModel,policyBudget} from '../../lib/routing-policy.mjs';
import {knownAlias,learnAction,validateAlias} from '../../lib/ha-aliases.mjs';
import {assertFocusedWrite,resolvedTargets} from '../../lib/ha-focus.mjs';
import {inferHAIntent} from '../../lib/ha-intent.mjs';
import {isFreeCoolingDown} from '../../lib/free-quota.mjs';
import {isLocationExplanation} from '../../lib/location-query.mjs';
import {procedureHint} from '../../lib/procedure-memory.mjs';
import {isStatusReport,REPORT_TOOL} from '../../lib/ha-reports.mjs';
import {installMediaRouter} from './media-routing.js';
import { appendFileSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import {findLearned,candidateFromSuccess,remember,disableLearned} from './learning.js';
import {findPhrase,rememberPhrase,phraseKindForTool} from './phrases.js';
const LOCAL={providerID:'evo-agent',id:'qwen36-agent'};
export const HA_TOTAL_MS=policyBudget('haTotalMs',15000);
export const HA_CLOUD_MS=policyBudget('cloudMs',120000);
export const HA_LOCAL_MS=Math.min(policyBudget('haLocalMs',12000),HA_TOTAL_MS-1000);
const routingMeta=s=>/\b(router|routing|openrouter)\b/.test(s)&&/^(?:please )?(?:explain|describe|how|what|which|tell me|do you know|are you aware|can you explain)\b/.test(s);
const coding=s=>/\b(write|implement|debug|develop|refactor|configure|install)\b.{0,45}\b(code|script|plugin|integration|server|config|automation)\b/.test(s)||/\b(read|open|inspect|review|compare|summarize)\b/.test(s)&&/(?:\/[^\s]+\.[a-z0-9]+\b|\b(?:files?|documents?|source code)\b)/.test(s);
const PEOPLE=/\b(shobha|shubha|somdutta|shivangsh|shivi|pecky)\b/;
const history=s=>{
 if(/\b(stock|news|flight|ticket|vacation|holiday)\b/.test(s))return false;
 if(/\b(visit\w*|locations?|where)\b/.test(s)&&/\b(today|yesterday|visited|history|locations|been|went)\b/.test(s))return true;
 return false;
};
const presence=s=>PEOPLE.test(s)&&!/\b(turn|switch|set|dim|lights?|fans?|thermostat)\b/.test(s)&&/\b(where\s+(?:is|are)|where'?s|current location|location|locate|home|away|zone)\b/.test(s)&&!/\b(yesterday|visited|visits|history|been|went|earlier|past|locations)\b/.test(s);
// Explicit physical controls may name an area or alias instead of a device noun.
export const isHAControl=text=>{
 const s=text.trim().toLowerCase().replace(/[.!?]+$/,'');
 if(/\b(server|service|process|computer|linux|windows|opencode|vllm|thinking|reasoning|notifications?|subscription|account|logging|debug|vpn|firewall)\b/.test(s))return false;
 return /^(?:please\s+)?(?:turn|switch)\s+(?:on|off)\s+(?!it$|them$|those$|both$|all of them$).+/.test(s)
  || /^(?:please\s+)?(?:turn|switch)\s+(?!it |them |those |both ).+\s+(?:on|off)$/.test(s);
};
const devices=s=>/\b(light\w*|dimmer\w*|fan\w*|thermostat|curtain\w*|blind\w*|switches?|devices?|entities|lamps?|den switch)\b/.test(s)&&/\b(on|off|state|status|dim|bright\w*|set|turn|switch|are|is)\b/.test(s);
export function isMixedRequest(text){
 const s=text.toLowerCase();if(coding(s)||routingMeta(s))return false;
 const clauses=s.split(/\s+(?:and|then|also)\s+(?=(?:turn|switch|set|run|show|share|summarize|analy[sz]e|provide|list|check)\b)/);
 if(clauses.length>1&&clauses.every(isHAControl))return false;
 if(clauses.length>1&&isHAControl(clauses[0]))return true;
 const media=/\b(video|footage|clip|ring|door\s?bell|camera|recording)\b/.test(s);
 return (devices(s)&&/\b(?:and|then|also)\s+(?:then\s+)?(?:turn|switch|set|run|show|share|analy[sz]e|provide|list|check)\b/.test(s)) || (history(s)&&devices(s)) || (media&&(history(s)||devices(s)||/\b(home assistant|homeassistant|ha mcp)\b/.test(s)));
}
export function classify(text){
 const s=text.toLowerCase();if(isTechnicalRequest(s)||isHAConfiguration(s)||coding(s)||routingMeta(s)||isLocationExplanation(s)||isMixedRequest(s))return null;
 if(presence(s))return 'devices';
 if(history(s))return 'history';
 if(isStatusReport(text))return 'devices';
 if(/\b(rooms?|bedrooms?|areas?|floors?)\b/.test(s)&&/\b(status|states?|what is|how is|check|show)\b/.test(s)&&!/\b(news|stock|hotel|booking|ticket|history|yesterday|why|explain)\b/.test(s))return 'devices';
 if(/\b(home assistant|homeassistant|ha mcp)\b/.test(s)||devices(s)||isHAControl(s))return 'devices';
 return null;
}
const isMcp=name=>/^(home[-_]assistant_|ha[-_]history_)/.test(name);
const allow=(name,kind)=>kind==='history'?/^ha[-_]history_/.test(name)||/GetDateTime$/.test(name):isMcp(name);
const isLocal=state=>state&&['history','devices'].includes(state.kind);
const key=id=>'ha-turn:'+id;
export const isHAFollowup=text=>/^(?:please )?(?:turn|switch)(?: it| them| those)?(?: back)? (?:on|off)[.!?]*$/i.test(text)||/^(?:please )?(?:(?:turn|switch|set|dim|make) (?:(?:on|off) )?(?:it|them|those|both)\b|(?:who|what|when|why|how)\b.{0,60}\b(?:it|them|those|they)\b|(?:and |what about )?(?:on|off|brighter|dimmer)\b|what about (?:yesterday|today)\b)/i.test(text);
const canonical=value=>JSON.stringify(value,(_k,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.entries(v).sort(([a],[b])=>a.localeCompare(b))):v);
export default {
 id:'ha-mcp-routing',
 async setup(ctx){
  const media=await installMediaRouter(ctx);
  const turns=new Map();
  onDiscard(async id=>{turns.delete(id);await ctx.storage?.remove(key(id));});
  const learningPath=ctx.options?.learningStore || homedir()+'/.local/share/opencode/ha-router/learned-routes.json';
  const phrasePath=ctx.options?.phraseStore || homedir()+'/.local/share/opencode/ha-router/learned-phrases.json';
  const stateFor=async id=>turns.get(id)||await ctx.storage?.get(key(id));
  const save=async(id,state)=>{turns.set(id,state);await ctx.storage?.set(key(id),JSON.parse(JSON.stringify(state)));};
  const log=obj=>{try{appendFileSync(homedir()+'/ha-local-debug/routing.jsonl',JSON.stringify({at:new Date().toISOString(),...obj})+'\n')}catch{}};
  const fallback=async(id,state,reason)=>{
   if(state.learnedRouteId){try{await disableLearned(learningPath,state.learnedRouteId,reason);}catch(error){log({event:'learning-error',reason:String(error.message||error)});}}
   state.cloudStartedAt||=Date.now();state.kind='fallback';state.reason=reason;state.fulfilled=true;delete state.requiredTool;
   await save(id,state);await ctx.session.switchModel({sessionID:id,model:cloudModel()});
   log({sessionID:id,event:'fallback',reason,model:cloudModel()});
  };
  await ctx.session.hook('prompt',async event=>{
   const promptStartedAt=Date.now();event.prompt.metadata={...(event.prompt.metadata||{}),opencodeStartedAt:promptStartedAt};
   let text=(event.prompt.text||'').trim().replace(/^["']|["']$/g,'');
   const prior=await stateFor(event.sessionID);
   const routeExplicit=async()=>{
if(cloudDirective(text)){
    const plain=withoutCloudDirective(text);
    const administrative=isTechnicalRequest(plain)||isHAConfiguration(plain)||forbidsTools(plain)||coding(plain.toLowerCase())||routingMeta(plain.toLowerCase());
    const semantic=administrative?null:await inferHAIntent(plain);
    const overrideKind=administrative||['configuration','investigation'].includes(semantic)?null:classify(plain)||(!isMixedRequest(plain)?semantic:null);
    await save(event.sessionID,{kind:['devices','history'].includes(overrideKind)?'fallback':'cloud-explicit',reason:'The user explicitly requested the configured cloud model',previous:cloudModel(),startedAt:Date.now(),calls:0,failures:0,requestText:text});
    await ctx.session.switchModel({sessionID:event.sessionID,model:cloudModel()});return true;
   }
    return false;
   };
   if(await routeExplicit())return;
   if(await media.prompt(event)){
    turns.delete(event.sessionID);await ctx.storage?.remove(key(event.sessionID));return;
   }
   text=(event.prompt.text||'').trim().replace(/^["']|["']$/g,'');
   if(await routeExplicit())return;
   if(isHAConfiguration(text)||isTechnicalRequest(text)){await save(event.sessionID,{kind:cloudDirective(text)?'cloud-explicit':'configuration',requestText:text});return;}
   if(forbidsTools(text)){await save(event.sessionID,{kind:'explanation',requestText:text});return;}
   const semanticScope=await inferHAIntent(text);
   if(['configuration','investigation'].includes(semanticScope)){await save(event.sessionID,{kind:semanticScope,requestText:text});return;}
   if(isLocationExplanation(text)){
    await save(event.sessionID,{kind:'explanation',requestText:text,previous:prior?.previous});
    if(prior?.previous){const restored=prior.previous.providerID==='opencode'&&isFreeCoolingDown()?cloudModel():prior.previous;await ctx.session.switchModel({sessionID:event.sessionID,model:restored});}
    return;
   }
   const implicitControl=isHAFollowup(text)&&/^(?:please )?(?:turn|switch)\b/i.test(text);
   const seeded=isHAFollowup(text)?(await ctx.session.get({sessionID:event.sessionID})).metadata?.haContextKind:null;
   const mixed=isMixedRequest(text);
   const baseKind=classify(text);
   const learned=!mixed&&!baseKind&&!coding(text.toLowerCase())?findLearned(learningPath,text):null;
   const phrase=!mixed&&!baseKind?findPhrase(phrasePath,text):null;
   const known=baseKind||learned?.route.kind||phrase?.kind||(implicitControl?'devices':null)||(['devices','history'].includes(seeded)?seeded:null)||(isLocal(prior)&&isHAFollowup(text)?prior.kind:null);
   const inferred=!mixed&&!known&&!coding(text.toLowerCase())&&!routingMeta(text.toLowerCase())&&!isHAFollowup(text)?await inferHAIntent(text):null;
   const kind=mixed?'orchestrate':known||inferred;
   if(kind==='orchestrate'){
    const session=await ctx.session.get({sessionID:event.sessionID});
    const child=session.agent==='ha';
    await save(event.sessionID,{kind:child?'fallback':kind,reason:child?'A mixed task must not be delegated intact':undefined,previous:prior?.previous||cloudModel(),startedAt:Date.now(),calls:0,failures:0});
    await ctx.session.switchModel({sessionID:event.sessionID,model:cloudModel()});
    log({sessionID:event.sessionID,event:'orchestrate',model:cloudModel()});return;
   }
   if(kind){
    const namedStatus=kind==='devices'?await namedStatusTarget(text):null;
    const reportOnly=!namedStatus&&kind==='devices'&&(isStatusReport(text)||isSimpleStatusQuery(text)&&/\b(status|states?|overview)\s*[.!?]*$/i.test(text));
    if(ctx.tool?.list){
     let ready=false;
     for(let attempt=0;attempt<40;attempt++){
      const catalog=await ctx.tool.list();
      const statusOnly=!!namedStatus||presence(text.toLowerCase())||kind==='devices'&&!/\b(all|every|everything|turn|toggle|set|dim|change|enable|disable|why|cause|history|when|automation|script|also)\b/i.test(text)&&/\b(status|state|is|are)\b/i.test(text)&&/\b(light|lights|fan|fans|switch|switches)\b/i.test(text);
      const requiredReady=reportOnly?catalog.some(tool=>tool.id===REPORT_TOOL):kind==='devices'&&!statusOnly?catalog.some(tool=>/^home[-_]assistant_/.test(tool.id)):catalog.some(tool=>allow(tool.id,kind));
      if(requiredReady && (!learned || catalog.some(tool=>tool.id===learned.route.requiredTool))){ready=true;break;}
      if(attempt===0&&ctx.tool.reload)await ctx.tool.reload();
      await new Promise(resolve=>setTimeout(resolve,250));
     }
     if(!ready){await fallback(event.sessionID,{previous:cloudModel(),startedAt:promptStartedAt,learnedRouteId:learned?.route.id},learned?'Learned route tool is unavailable':'HA MCP catalog unavailable');return;}
    }
    const session=await ctx.session.get({sessionID:event.sessionID});
    const state={kind,previous:prior?.previous||session.model,broad:/\b(all|every|everything)\b/i.test(text),target:undefined,fulfilled:false,startedAt:promptStartedAt,calls:0,failures:0,failureCounts:{}};
    state.statusTarget=namedStatus;
    state.fastStatus=!!namedStatus||kind==='devices'&&!mixed&&/\b(status|state|is|are)\b/i.test(text)&&(/\b(light|lights|fan|fans|switch|switches)\b/i.test(text)||/\blive state only\b|\b(?:status|state) of\b/i.test(text))&&(!/\b(room|area|floor)\b/i.test(text)||/\b(dimmers?|lights?|switches?|fans?|sensors?|thermostats?)\b/i.test(text))&&!state.broad&&!/\b(turn|toggle|set|dim|change|enable|disable|why|cause|history|when|automation|script|and then|also)\b/i.test(text);
    const alias=knownAlias(text);if(alias){state.alias=alias;state.target=alias.name;state.requiredTool='home-assistant_intent__HassTurn'+(/\boff\b/i.test(text)?'Off':'On');}
    state.focusGroups=prior?.focusGroups||[];state.referenceFollowup=!!session.metadata?.haReferenceFollowup||implicitControl;
    state.focusTargets=session.metadata?.haReferenceFollowup?(session.metadata.haFocusTargets||[]):implicitControl?(/\bboth\b/i.test(text)?(state.focusGroups.length>=2?state.focusGroups.slice(-2).flatMap(g=>g.targets):[]):prior?.focusTargets||[]):[];
    state.requestText=text;state.reportOnly=reportOnly;state.presence=presence(text.toLowerCase());
    if(state.presence)state.fastStatus=true;
    if(kind==='history')state.requiredTool='ha-history_get_visited_locations';
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
    if(prior?.previous)await ctx.session.switchModel({sessionID:event.sessionID,model:prior.previous.providerID==='opencode'&&isFreeCoolingDown()?cloudModel():prior.previous});
   }
   if(turns.size>1000)turns.delete(turns.keys().next().value);
  });
  await ctx.session.hook('context',async event=>{
   if(isDiscarded(event.sessionID))throw new Error('This rejected session was discarded. Start a fresh session.');
   captureTools(event.sessionID,event.tools);
   if(await media.active(event.sessionID))return;
   let state=await stateFor(event.sessionID);
   if(expandedCapabilities(event.sessionID)){
    restoreSelected(event.sessionID,event.tools);
    if(state){state.kind='discovered';delete state.requiredTool;await save(event.sessionID,state);}
    event.system.push({type:'text',text:DISCOVERY_RULE});return;
   }
   if(!state){
    const session=await ctx.session.get({sessionID:event.sessionID});
    if(session.agent==='ha'){
     state={kind:'devices',previous:cloudModel(),calls:0,failures:0,failureCounts:{},startedAt:Date.now(),fulfilled:false};
     await save(event.sessionID,state);
    }
   }
   if(!state||['explanation','cloud-explicit','configuration','investigation'].includes(state.kind))return;
   if(['orchestrate','fallback'].includes(state.kind)){
    state.cloudCalls=(state.cloudCalls||0)+1;await save(event.sessionID,state);
    if(state.cloudCalls>10)throw new Error('the configured cloud model coordination reached its step limit; report unresolved tasks instead of looping.');
   }
   if(state.kind==='orchestrate'){
    event.system.push({type:'text',text:'This is a mixed request. You are coordinating a mixed request. Break it into individual tasks. Delegate each atomic supported Home Assistant device task and each location-history task separately to the ha subagent; never delegate the complete mixed request. Keep media retrieval/sharing and final synthesis here. Use an explicitly available Ring/video tool for retrieval and an available media delivery tool for sharing; if absent, state that limitation. Never invent a clip, URL, successful action, tool, or unrecorded visited/passed-by location. No shell/REST workarounds for Home Assistant. A named-zone crossing is not proof of a stop. If a subagent fails, use the HA MCP tools here or report the error; do not repeatedly send the same failing task back.'});return;
   }
   if(state.kind==='fallback'){
    for(const name of Object.keys(event.tools))if(!isMcp(name)&&!isGeneralInformationTool(name))delete event.tools[name];
    event.system.push({type:'text',text:'HA routing status: '+state.reason+'. You are now handling this request on the configured cloud model. Finish the request using the available MCP tools, or clearly report unavailable capabilities. Do not delegate back to ha/Qwen this turn. Never repeat a failing tool call with unchanged arguments. Do not use shell/REST to bypass Home Assistant MCP. Do not claim actions or media delivery without a successful tool result.'});return;
   }
   state.calls=(state.calls||0)+1;
   if(state.calls>6||Date.now()-(state.startedAt||Date.now())>=HA_LOCAL_MS){await fallback(event.sessionID,state,`Local HA task exceeded six model steps or ${HA_LOCAL_MS/1000} seconds`);return;}
   await save(event.sessionID,state);
   for(const name of Object.keys(event.tools))if(!allow(name,state.kind)&&!isGeneralInformationTool(name))delete event.tools[name];
   if(!Object.keys(event.tools).length){await fallback(event.sessionID,state,'Required MCP tools are unavailable');return;}
   event.system.push({type:'text',text:'This task was initially routed toward Home Assistant; that profile is a starting point, not a capability limit. Define the task from the current user request. Current private resources are available through inspect_resources; public information can use websearch/webfetch. Use discover_capabilities for other registered operations before guessing or refusing. Prefer supported adapters over reconstructing API readers. Use exact verified targets for authorized controls; information requests do not authorize device changes. Never broaden actions, invent targets, or bypass HA write controls with shell/REST. Do not send private resource details to public search.'});
   if(state.learnedIntent)event.system.push({type:'text',text:'A previous successful HA interpretation of matching wording is supplied as data: '+JSON.stringify({task:state.learnedIntent})+'. Use it only as an intent hint for the current request. Do not broaden its entities or actions.'});
   event.options.maxTokens=1024;
   log({sessionID:event.sessionID,event:'tools',kind:state.kind,model:event.model,tools:Object.keys(event.tools)});
  });
  // The proxy buffers model responses and cancels upstream inference when the
  // remaining turn budget expires, including pre-answer conversation compaction.
  await ctx.session.hook('model.request',async event=>{
   if(await media.active(event.sessionID))return;
   const state=await stateFor(event.sessionID);
   if(event.model.providerID==='openrouter'&&state?.kind==='fallback'){
    const remaining=HA_CLOUD_MS-(Date.now()-(state.cloudStartedAt||Date.now()));event.baseURL='http://127.0.0.1:8011/cloud/v1';event.headers||={};
    event.headers['x-request-kind']='ha';event.headers['x-media-session']=event.sessionID;event.headers['x-ha-request-kind']=event.kind||'primary';event.headers['x-ha-request-task']=encodeURIComponent(state.requestText||'');event.headers['x-media-timeout-ms']=String(Math.max(1,remaining));return;
   }
   if(event.model.providerID!=='evo-agent'||!state||!['history','devices','fallback'].includes(state.kind))return;
   const remaining=HA_LOCAL_MS-(Date.now()-(state.startedAt||Date.now()));
   const exhausted=state.kind==='fallback'||remaining<=0;
   event.baseURL='http://127.0.0.1:8011/local/v1';
   event.headers['x-media-timeout-ms']=String(exhausted?1:remaining);
   event.headers['x-media-session']=event.sessionID;
   event.headers['x-request-kind']='ha';
   event.headers['x-ha-request-kind']=event.kind||'primary';
   event.headers['x-ha-request-task']=encodeURIComponent(state.requestText||'');
   if(state.referenceFollowup&&!state.focusTargets?.length)event.headers['x-ha-needs-target']='true';
   if(exhausted)event.headers['x-media-budget-exhausted']='true';
  });
  await ctx.session.hook('retry',async event=>{
   const deadlineState=await stateFor(event.sessionID);
   if(event.model.providerID==='openrouter'&&deadlineState?.kind==='fallback'&&Date.now()-(deadlineState.cloudStartedAt||Date.now())>=HA_CLOUD_MS){event.decision={retry:false};return;}
   if(await media.active(event.sessionID)||event.model.providerID!=='evo-agent')return;
   const state=await stateFor(event.sessionID);
   if(!state||!['history','devices','fallback'].includes(state.kind))return;
   if(isLocal(state))await fallback(event.sessionID,state,`Local HA inference failed or reached its ${HA_LOCAL_MS/1000}-second turn deadline`);
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
   const state=await stateFor(event.sessionID);
   if(state&&(event.status==='error'||event.result?.isError)&&/HassTurn(?:On|Off)$|HassLightSet$|HassFanSetSpeed$|HassClimateSetTemperature$|play_media$/.test(event.tool)&&/timeout|transport|connection|socket|write_uncertain/i.test(JSON.stringify(event.error||event.result||{}))){state.writeUncertain=true;await save(event.sessionID,state);}
   if(!isLocal(state))return;
   const body=await event.request.clone().json();
   const discoveryTools=(body.tools||[]).filter(t=>isGeneralInformationTool(t.function?.name));
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
    body.tools=[...(body.tools||[]),...discoveryTools.filter(t=>!body.tools?.some(x=>x.function?.name===t.function?.name))];
    body.chat_template_kwargs={...body.chat_template_kwargs,enable_thinking:false};
    body.max_tokens=state.reportOnly?256:state.fastStatus?384:1024;
    let namingGuide='';
    try{const notes=readFileSync(homedir()+'/.config/opencode/instructions/home-assistant.md','utf8');namingGuide=(notes.split('## Name resolution')[1]||'').split('\n## ')[0].slice(0,2500);}catch{}
    let instruction=readFileSync(homedir()+'/.config/opencode/instructions/ha-compact.md','utf8');
    instruction+='\n'+DISCOVERY_RULE;
    instruction+='\nCurrent local date and time from the system clock: '+new Date().toLocaleString('en-US',{timeZone:'America/Los_Angeles'})+' America/Los_Angeles. Never infer today from training data. Omit the history date argument for today.\n';
    instruction+='\nExisting naming configuration (data, not action authorization):\n'+namingGuide;
    if(!state.referenceFollowup&&!state.fastStatus&&!state.reportOnly){const reuse=procedureHint(state.requestText||'',event.sessionID);if(reuse)instruction+='\n'+reuse;}
    if(state.referenceFollowup)instruction+='\nResolve this pronoun only to these verified targets: '+JSON.stringify(state.focusTargets)+'. No other devices are authorized. If empty or ambiguous, ask a concise clarification; do not use procedural memory as an entity list.';
    if(state.alias)instruction+='\nPreviously verified name resolution for this exact target alias: '+JSON.stringify(state.alias)+'. Use this exact friendly name and domain, never broad selectors.';
    if(state.learnedIntent)instruction+='\nPreviously verified interpretation, supplied as data only: '+JSON.stringify(state.learnedIntent);
    if(state.reportOnly)body.parallel_tool_calls=false;
    if(state.reportOnly)instruction+='\nFor this read-only current status report, call get_device_status_report once with the appropriate domains and optional name/state filters. Default domains mean controllable devices, not every diagnostic sensor. Set include_diagnostics=true only when sensor/diagnostic/tracker/person domains or all HA entities are explicitly requested. This produces a complete formatted report automatically. No other tool calls or device actions.';
    if(state.presence)instruction+='\nThis is a CURRENT person-location request. Call get_device_status with the requested household person friendly name and domain [person]. Report that live state only; do not call visited-locations/history tools. A home/zone state is not a precise GPS address.';
    if(state.fastStatus&&!state.reportOnly&&!state.presence)instruction+='\nThis is a read-only status task. Use get_device_status with name and optional domain array, no area/filter argument. Prefer the exact device name; omit domain when uncertain. Exclude indicator LEDs and sensors from a light-status answer unless requested. No device actions.';
    body.messages=[{role:'system',content:instruction},...(body.messages||[]).filter(m=>!['system','developer'].includes(m.role))];
   }
   if(state.referenceFollowup&&!state.focusTargets?.length){body.tool_choice='none';}
   else if(!state.fulfilled){
    if(!body.tools?.length)throw new Error('HA MCP tool definitions missing.');
    if(state.requiredTool&&body.tools.some(t=>t.function?.name===state.requiredTool))body.tools=body.tools.filter(t=>t.function?.name===state.requiredTool||isGeneralInformationTool(t.function?.name));
    body.tool_choice='required';
   }
   event.request=new Request(event.request,{body:JSON.stringify(body)});
  });
  await ctx.tool?.hook('execute.before',async event=>{
   if(isGeneralInformationTool(event.tool)&&!isDiscoveryTool(event.tool)){
    const st=await stateFor(event.sessionID);
    if(st&&['devices','history','fallback'].includes(st.kind)){selectCapabilities(event.sessionID,[event.tool]);st.kind='discovered';st.fulfilled=true;delete st.requiredTool;await save(event.sessionID,st);}
   }
  });
  await ctx.tool?.hook('execute.after',async event=>{
   if(isDiscarded(event.sessionID))return;
   if(event.status==='completed'&&/HassTurn(?:On|Off)$/.test(event.tool)){try{const st=await stateFor(event.sessionID);let query=st?.requestText;if(!query){const messages=await ctx.session.context({sessionID:event.sessionID});query=messages.filter(m=>m.type==='user').at(-1)?.text;}if(query)await learnAction(query,event.tool,event.input||{},event.result||{});}catch{}}
   if(event.tool==='subagent' && event.status==='completed' && event.input?.agent==='ha'){
    try{
     const parent=await ctx.session.get({sessionID:event.sessionID});
     const messages=await ctx.session.context({sessionID:event.sessionID});
     const text=(messages.filter(m=>m.type==='user').at(-1)?.text || '').trim().replace(/^["']|["']$/g,'');
     const childID=event.result?.metadata?.sessionID;
     if(parent.model?.id?.includes('deepseek') && childID && !isMixedRequest(text) && !classify(text) && !coding(text.toLowerCase())){
      const child=await ctx.session.context({sessionID:childID});
      const calls=child.filter(m=>m.type==='assistant'&&!m.error).flatMap(m=>(m.content||[]).filter(c=>c.type==='tool'));
      const verified=calls.length&&calls.every(c=>c.state?.status==='completed'&&phraseKindForTool(c.name||c.tool,c.state));
      if(verified&&!isHAFollowup(text)&&!isLocationExplanation(text)){
       const kind=calls.every(c=>phraseKindForTool(c.name||c.tool,c.state)==='history')?'history':'devices';
       rememberPhrase(phrasePath,text,kind,calls.map(c=>c.state?.input||{}));
       log({sessionID:event.sessionID,event:'delegated-phrase-learned',kind,text:text.slice(0,120)});
      }
      const candidate=candidateFromSuccess({text,task:event.input.prompt,child});
      if(candidate && await remember(learningPath,candidate))log({sessionID:event.sessionID,event:'learned',routeID:candidate.id,kind:candidate.kind});
      else log({sessionID:event.sessionID,event:'learn-skipped',reason:'Delegation did not meet verified MCP/entity requirements'});
     }
    }catch(error){log({sessionID:event.sessionID,event:'learning-error',reason:String(error.message || error)});}
   }
   // Cloud-served HA work: remember this exact wording so it goes local next time.
   if(isMcp(event.tool)&&event.status==='completed'){
    const cloudState=await stateFor(event.sessionID);
    if(!isLocal(cloudState)){
     try{
      const session=await ctx.session.get({sessionID:event.sessionID});
      const prov=session?.model?.providerID;
      if(prov&&prov!=='evo-agent'&&prov!=='evo-vision'){
       const messages=await ctx.session.context({sessionID:event.sessionID});
       const text=(messages.filter(m=>m.type==='user').at(-1)?.text||'').trim().replace(/^["']|["']$/g,'');
       const phraseKind=phraseKindForTool(event.tool,event.result||{});
       if(text&&phraseKind&&!isHAFollowup(text)&&!/^You are a subagent/i.test(text)&&!isLocationExplanation(text)&&!routingMeta(text.toLowerCase())&&rememberPhrase(phrasePath,text,phraseKind,[event.input||{}]))log({sessionID:event.sessionID,event:'phrase-learned',kind:phraseKind,text:text.slice(0,120)});
      }
     }catch(error){log({sessionID:event.sessionID,event:'phrase-learn-error',reason:String(error.message||error)});}
    }
   }
   const state=await stateFor(event.sessionID);
   if(state&&(event.status==='error'||event.result?.isError)&&/HassTurn(?:On|Off)$|HassLightSet$|HassFanSetSpeed$|HassClimateSetTemperature$|play_media$/.test(event.tool)&&/timeout|transport|connection|socket|write_uncertain/i.test(JSON.stringify(event.error||event.result||{}))){state.writeUncertain=true;await save(event.sessionID,state);}
   if(!isLocal(state))return;
   if(event.status==='completed'&&allow(event.tool,state.kind)&&!state.referenceFollowup){
    const targets=resolvedTargets(event.tool,{...(event.result||{}),input:event.input||{}});
    if(targets.length){state.focusGroups||=[];let group=state.focusGroups.at(-1);if(!group||group.query!==state.requestText){group={query:state.requestText,targets:[]};state.focusGroups.push(group);}group.targets=[...new Map([...group.targets,...targets].map(t=>[JSON.stringify(t),t])).values()];state.focusGroups=state.focusGroups.slice(-2);state.focusTargets=group.targets;}
   }
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
   if(state&&['history','devices','fallback'].includes(state.kind)&&isMcp(event.tool)&&(isLocal(state)?HA_LOCAL_MS-(Date.now()-(state.startedAt||Date.now())):HA_CLOUD_MS-(Date.now()-(state.cloudStartedAt||Date.now())))<5000){
    if(isLocal(state)){await fallback(event.sessionID,state,'Insufficient remaining local HA budget to start another network tool safely');throw new Error('Local budget reached before this tool executed. No HA request was sent by this call. Continue on the configured cloud model and execute this still-pending operation there; preserve completed results and never repeat uncertain writes.');}
    throw new Error('Cloud recovery budget reached; completion is unconfirmed. Do not start further calls or claim success.');
   }
   if(state?.writeUncertain&&isMcp(event.tool)&&!/^ha[-_]history_|GetLiveContext$|GetDateTime$|search_media$/.test(event.tool))throw new Error('A previous write result is uncertain. Do not repeat it automatically; read state and report uncertainty.');
   if(event.tool===REPORT_TOOL&&isSimpleStatusQuery(state?.requestText||''))event.input=await resolveReportScope(state.requestText,event.input||{});
   assertFocusedWrite(event.tool,event.input,state);
   const mutation=isMcp(event.tool)&&!/^ha[-_]history_|GetLiveContext$|GetDateTime$|search_media$/.test(event.tool);
   if(mutation&&!event.input?.name&&!event.input?.area&&!event.input?.floor&&!state?.broad)throw new Error('A device action requires an explicit verified target; an unrequested domain-wide action is not allowed.');
   if(mutation&&/\blights?\b/i.test(state?.requestText||'')&&!/HassTurn(?:On|Off)$|HassLightSet$/.test(event.tool))throw new Error('A light request cannot operate unrelated media or other device domains.');
   if(/HassTurn(?:On|Off)$/.test(event.tool)&&!event.input?.name&&!event.input?.area&&!event.input?.floor&&!state?.target&&!state?.broad)throw new Error('An explicit device name or area is required; an unnamed group action needs explicit authorization.');
   if(!isLocal(state))return;
   if(state.statusTarget&&event.tool==='ha-history_get_device_status')event.input={name:state.statusTarget.name,domain:state.statusTarget.domain};
   if(state.reportOnly&&event.tool===REPORT_TOOL){
    const q=(state.requestText||'').toLowerCase(),positive=q.split(/\b(?:not|except|excluding)\b/)[0];event.input={...event.input};
    if(!/\b(sensors?|diagnostics?|trackers?|persons?|people|entities)\b/.test(positive))event.input.include_diagnostics=false;
    if(/\blights?\b/.test(positive)&&!/\b(devices|entities|switches|sensors|fans)\b/.test(positive))event.input.domains=['light'];
    if(/\b(all|every|whole)\b/.test(q))event.input.limit=200;
    const states=['on','off','unavailable','unknown'].filter(x=>new RegExp('\\b'+x+'\\b').test(positive));
    if(states.length===1)event.input.state=states[0];else delete event.input.state;
   }
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
   if(state.alias&&/HassTurn(?:On|Off)$/.test(event.tool)){event.input=await validateAlias(state.alias);}
  });
  await ctx.permission.hook('evaluate',async event=>{
   const state=await stateFor(event.sessionID);
   if(isLocal(state)&&!allow(event.action,state.kind)){event.effect='deny';event.message='Local HA tasks must use their supplied MCP tools. Repeated failures fall back to the configured cloud model.';}
  });
 }
};
