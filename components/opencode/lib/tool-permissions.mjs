// Routing/discovery never grants permissions. Native allow/ask/deny still applies.
import {instructionText} from './user-scope.mjs';
export const isDiscoveryTool=name=>['discover_capabilities','inspect_resources'].includes(name);
export const isGeneralInformationTool=name=>isDiscoveryTool(name)||['websearch','webfetch'].includes(name);
export const isHAOperation=name=>/^(home[-_]assistant_|ha[-_]history_)/.test(name||'');
const scopeText=state=>instructionText(state?.requestText||'').replace(/[‘’]/g,"'");
const globalReadOnly=state=>/\bread[ -]only\b|\b(?:do not|don't|never)\s+(?:make\s+(?:any\s+)?changes|(?:change|modify|operate)\s+anything)\b|\bno changes\b/i.test(scopeText(state));
export const isReadOnlyTask=state=>{
 const explicit=/\bread[ -]only\b|\b(?:do not|don't|never)\s+(?:make\s+(?:any\s+)?changes|(?:change|modify|operate)\s+(?:any\s+)?(?:device\s+)?(?:anything|states?|devices?|settings?))\b|\bno changes\b/i.test(scopeText(state));
 if(explicit||state?.kind==='fallback')return explicit;
 return state?.kind==='history'||!!(state?.fastStatus||state?.presence||state?.reportOnly);
};
export const isHAWrite=name=>isHAOperation(name)&&!/^ha[-_]history_/.test(name)&&!/GetLiveContext$|GetDateTime$|search_media$/.test(name);
export function allowsTaskTool(name,state){
 if(isReadOnlyTask(state)&&isHAWrite(name))return false;
 if(globalReadOnly(state)&&['write','edit','apply_patch'].includes(name))return false;
 // A route/profile is a tool-list optimization, never an execution allowlist.
 // This default does not override native registry or allow/ask/deny decisions.
 return true;
}

export async function assertDiscoveryPermission(ctx,name,input,context){
 if(typeof ctx.permission?.assert!=='function')throw new Error('Native permission evaluation is unavailable; discovery was not executed.');
 const resource=name==='discover_capabilities'?'catalog':String(input.adapter||'home-assistant')+':'+String(input.resource||'entities');
 await ctx.permission.assert({sessionID:context.sessionID,agent:context.agent,action:name,
  resources:[resource],save:[resource],metadata:input,
  ...(context.messageID&&context.id?{source:{type:'tool',messageID:context.messageID,id:context.id}}:{})});
 if(context.signal?.aborted)throw new Error('Discovery was cancelled before execution.');
}
