import {onDiscard} from './session-lifecycle.mjs';
const sessions=new Map();
export const isDiscoveryTool=name=>['discover_capabilities','inspect_resources'].includes(name);
export const isGeneralInformationTool=name=>isDiscoveryTool(name)||['websearch','webfetch'].includes(name);
export const DISCOVERY_RULE='Capability discovery: use discover_capabilities to inspect the live registered tool catalog and exact argument schemas before claiming a capability is unavailable or guessing an API. inspect_resources reads current resource names, identities and relationships from registered read-only adapters; its entities resource already joins device, entity-area, device-area, effective area and floor IDs. Prefer these declared interfaces over guessing API paths. A narrowed task profile does not describe the whole system. Discovery can enable registered tools from the current agent context for the next step; user permissions and explicit task constraints still apply. An information request does not authorize a device or configuration change. Never use a mutating operation to retrieve information. Resolve missing user-scoped names, locations and scope through resource discovery or ask; do not invent them from public search results. Tool registration is not proof of service reachability. Never infer absence from a partial page or treat old model answers as source evidence.';
export const EVIDENCE_RULE='Evidence discipline: live or changing facts require actual task-scoped retrieval. Do not invent API responses, measurements, dates, prices, forecasts or source coverage. A previous assistant answer, conversation summary or catalog registration is not retrieved evidence. Resolve required scope before searching. After a clarification, fetch evidence for the clarified parameters. If retrieval fails or coverage is incomplete, state that limit or ask; never fill gaps with plausible values or attribute unperformed calls to a source.';
export function captureTools(id,tools){let s=sessions.get(id);if(!s){s={baseline:{},selected:new Set()};sessions.set(id,s);}for(const [name,tool] of Object.entries(tools||{}))s.baseline[name]=tool;return s;}
export function clearDiscovery(id){sessions.delete(id);}
export function selectedCapabilities(id){return sessions.get(id)?.selected||new Set();}
export function expandedCapabilities(id){return selectedCapabilities(id).size>0;}
export function selectCapabilities(id,names){
 const s=sessions.get(id);const enabled=[],unavailable=[];
 for(const name of names||[])if(s?.baseline[name]){s.selected.add(name);enabled.push(name)}else unavailable.push(name);
 return {enabled,unavailable,note:'Enabled tools remain subject to native permissions and current user authorization. No operation has been executed.'};
}
export function restoreSelected(id,tools){const s=sessions.get(id);for(const name of s?.selected||[])if(s.baseline[name])tools[name]=s.baseline[name];}
export function catalogPage(registered,{query='',names=[],offset=0,limit=15,schemas=false,available=[]}={}){
 const terms=query.toLowerCase().match(/[\p{L}\p{N}_]+/gu)||[],allowed=new Set(available);
 let rows=registered.map(t=>({name:t.id||t.name,description:t.description||'',schema:t.input||t.parameters||t.inputSchema||{},enabledInCurrentAgent:allowed.has(t.id||t.name)})).filter(x=>x.name);
 if(names.length)rows=rows.filter(x=>names.includes(x.name));
 else {rows=rows.filter(x=>x.name!=='discover_capabilities').map(x=>({...x,score:terms.reduce((n,w)=>n+(x.name.toLowerCase().includes(w)?3:0)+(x.description.toLowerCase().includes(w)?1:0),0)+(isGeneralInformationTool(x.name)?0.1:0)})).sort((a,b)=>b.score-a.score||a.name.localeCompare(b.name));}
 // Zero keyword hits are not proof of missing capability: include catalog fallbacks.
 const total=rows.length;rows=rows.slice(offset,offset+limit).map(({schema,score,...x})=>({...x,description:x.description.slice(0,schemas?1800:280),...(schemas?{schema}:{})}));
 return {asOf:new Date().toISOString(),tools:rows,total,offset,nextOffset:offset+rows.length<total?offset+rows.length:null,partial:offset>0||offset+rows.length<total,scope:'Live registration catalog; enabledInCurrentAgent distinguishes tools that can be selected from this agent context. Registration does not establish reachability.',resourceAdapters:[{id:'home-assistant',readOnly:true,resources:['entities','devices','areas','floors'],tool:'inspect_resources'}]};
}
onDiscard(clearDiscovery);
