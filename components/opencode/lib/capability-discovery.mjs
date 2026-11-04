import {onDiscard} from './session-lifecycle.mjs';
const sessions=new Map();
import {isDiscoveryTool,isGeneralInformationTool} from './tool-permissions.mjs';
export {isDiscoveryTool,isGeneralInformationTool};
export function captureTools(id,tools,{replace=false,allows}={}){let s=sessions.get(id);if(!s){s={baseline:{},selected:new Set(),allows:()=>true};sessions.set(id,s);}if(replace)s.baseline={};if(allows)s.allows=allows;for(const [name,tool] of Object.entries(tools||{}))s.baseline[name]=tool;if(replace)for(const name of s.selected)if(!s.baseline[name]||!s.allows(name))s.selected.delete(name);return s;}
export function availableCapabilities(id){const s=sessions.get(id);return Object.keys(s?.baseline||{}).filter(name=>s.allows(name));}
export function clearDiscovery(id){sessions.delete(id);}
export function selectedCapabilities(id){return sessions.get(id)?.selected||new Set();}
export function expandedCapabilities(id){return selectedCapabilities(id).size>0;}
export function selectCapabilities(id,names){
 const s=sessions.get(id);const enabled=[],unavailable=[];
 for(const name of names||[])if(s?.baseline[name]&&s.allows(name)){s.selected.add(name);enabled.push(name)}else unavailable.push(name);
 return {enabled,unavailable,note:'Enabled tools remain subject to native permissions and current user authorization. No operation has been executed.'};
}
export function restoreSelected(id,tools){const s=sessions.get(id);for(const name of s?.selected||[])if(s.baseline[name]&&s.allows(name))tools[name]=s.baseline[name];}
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
