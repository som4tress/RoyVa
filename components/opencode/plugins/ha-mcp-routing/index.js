import {isHAConfiguration,isTechnicalRequest} from '../../lib/user-scope.mjs';
import {isLocationExplanation} from '../../lib/location-query.mjs';
import {isStatusReport} from '../../lib/ha-reports.mjs';
import {allowsTaskTool,isReadOnlyTask} from '../../lib/tool-permissions.mjs';
import {assertFocusedWrite,resolvedTargets} from '../../lib/ha-focus.mjs';
import {captureTools,restoreSelected} from '../../lib/capability-discovery.mjs';
import {onDiscard} from '../../lib/session-lifecycle.mjs';
import {installMediaRouter} from './media-routing.js';
import {policyBudget} from '../../lib/routing-policy.mjs';
export const HA_LOCAL_MS=policyBudget('generalLocalMs',60000);
export const HA_TOTAL_MS=HA_LOCAL_MS;
export const HA_CLOUD_MS=policyBudget('cloudMs',120000);
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
export const isHAFollowup=text=>/^(?:please )?(?:turn|switch)(?: it| them| those)?(?: back)? (?:on|off)[.!?]*$/i.test(text)||/^(?:please )?(?:(?:turn|switch|set|dim|make) (?:(?:on|off) )?(?:it|them|those|both)\b|(?:who|what|when|why|how)\b.{0,60}\b(?:it|them|those|they)\b|(?:and |what about )?(?:on|off|brighter|dimmer)\b|what about (?:yesterday|today)\b)/i.test(text);
export default {id:'ha-mcp-routing',async setup(ctx){
 const turns=new Map();
 onDiscard(id=>turns.delete(id));
 const media=await installMediaRouter(ctx);
 await ctx.session.hook('prompt',async event=>{
  event.prompt.metadata={...(event.prompt.metadata||{}),opencodeStartedAt:Date.now()};
  if(await media.prompt(event))return;
  const requestText=event.prompt.text||'',prior=turns.get(event.sessionID);
  const session=await ctx.session.get({sessionID:event.sessionID});
  // Keep authorization/reference checks, without choosing tools, rewriting inputs,
  // changing the system prompt, or imposing a second model deadline.
  turns.set(event.sessionID,{requestText,kind:classify(requestText),
   broad:/\b(all|every|everything)\b/i.test(requestText),
   reportOnly:isStatusReport(requestText),
   referenceFollowup:!!session.metadata?.haReferenceFollowup||isHAFollowup(requestText),
   focusTargets:prior?.focusTargets?.length?prior.focusTargets:session.metadata?.haFocusTargets||[]});
 });
 await ctx.session.hook('context',event=>{
  const state=turns.get(event.sessionID);
  // Reflect explicit current-request restrictions in the catalog as well as execution.
  // Do not infer a tool profile from task kind, device names, model or frontend.
  const scope={requestText:state?.requestText||''};
  if(isReadOnlyTask(scope))for(const name of Object.keys(event.tools))if(!allowsTaskTool(name,scope))delete event.tools[name];
  captureTools(event.sessionID,event.tools,{replace:true,allows:name=>allowsTaskTool(name,scope)});restoreSelected(event.sessionID,event.tools);
 });
 await ctx.tool?.hook('execute.before',async event=>{
  const state=turns.get(event.sessionID);
  if(!allowsTaskTool(event.tool,state))throw new Error('This request is read-only; a write requires a new explicit instruction.');
  if(state?.writeUncertain&&isMcp(event.tool)&&!/^ha[-_]history_|GetLiveContext$|GetDateTime$|search_media$/.test(event.tool))throw new Error('A previous write result is uncertain. Do not repeat it automatically; read state and report uncertainty.');
  assertFocusedWrite(event.tool,event.input,state);
  const mutation=isMcp(event.tool)&&!/^ha[-_]history_|GetLiveContext$|GetDateTime$|search_media$/.test(event.tool);
  if(mutation&&!event.input?.name&&!event.input?.area&&!event.input?.floor&&!state?.broad)throw new Error('A device action requires an explicit verified target; an unrequested domain-wide action is not allowed.');
  if(mutation&&/\blights?\b/i.test(state?.requestText||'')&&!/HassTurn(?:On|Off)$|HassLightSet$/.test(event.tool))throw new Error('A light request cannot operate unrelated media or other device domains.');
  if(/HassTurn(?:On|Off)$/.test(event.tool)&&!event.input?.name&&!event.input?.area&&!event.input?.floor&&!state?.broad)throw new Error('An explicit device name or area is required; an unnamed group action needs explicit authorization.');
 });
 await ctx.tool?.hook('execute.after',event=>{
  const state=turns.get(event.sessionID);if(!state)return;
  if((event.status==='error'||event.result?.isError)&&/HassTurn(?:On|Off)$|HassLightSet$|HassFanSetSpeed$|HassClimateSetTemperature$|play_media$/.test(event.tool)&&/timeout|transport|connection|socket|write_uncertain/i.test(JSON.stringify(event.error||event.result||{})))state.writeUncertain=true;
  if(event.status==='completed'){
   const targets=resolvedTargets(event.tool,{...(event.result||{}),input:event.input||{}});
   if(targets.length)state.focusTargets=targets;
  }
 });
 await ctx.permission.hook('evaluate',event=>{
  if(event.source?.type==='tool'&&!allowsTaskTool(event.action,turns.get(event.sessionID))){event.effect='deny';event.message='This request is read-only; a write requires a new explicit instruction.';}
 });
}};
