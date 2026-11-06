import {spawn} from 'node:child_process';
import {catalogPage,captureTools,clearDiscovery,availableCapabilities} from '../../lib/capability-discovery.mjs';
import {assertDiscoveryPermission} from '../../lib/tool-permissions.mjs';
import {clearCompletionCheck} from '../../lib/completion-check.mjs';
export default {id:'capability-discovery',async setup(ctx){
 await ctx.tool.transform(editor=>{
  editor.add({options:{codemode:false},name:'discover_capabilities',description:'Discover live registered tools, supported operations and exact input schemas. Use before capability refusals, API guesses or crossing a narrow task profile. Optionally enable named tools from the current agent context for the next step; this executes no operation and does not bypass permissions.',input:{type:'object',properties:{query:{type:'string',maxLength:200},names:{type:'array',items:{type:'string'},maxItems:10},enable:{type:'array',items:{type:'string'},maxItems:10},schemas:{type:'boolean'},offset:{type:'integer',minimum:0},limit:{type:'integer',minimum:1,maximum:30}},additionalProperties:false},execute:async(input,context)=>{
   await assertDiscoveryPermission(ctx,'discover_capabilities',input,context);
   const {selectCapabilities}=await import('../../lib/capability-discovery.mjs');
   const catalog=await ctx.tool.list();captureTools(context.sessionID,{});
   const available=availableCapabilities(context.sessionID);
   const page=catalogPage(catalog.filter(t=>available.includes(t.id||t.name)),{...input,available});
   if(input.enable?.length)page.selection=selectCapabilities(context.sessionID,input.enable);
   return {content:JSON.stringify(page)};
  }});
  editor.add({options:{codemode:false},name:'inspect_resources',description:'Discover current resource names, stable IDs, state and relationships using a registered read-only adapter. Supports entities/devices/areas/floors with explicit scope and pagination. Use discovery rather than inventing aliases, assuming missing capabilities, or guessing ownership. No configuration or device changes.',input:{type:'object',properties:{adapter:{type:'string',enum:['home-assistant']},resource:{type:'string',enum:['entities','devices','areas','floors']},query:{type:'string',maxLength:200,description:'Case-insensitive substring search, also ignoring punctuation/spacing, of identity and location fields: IDs, current/original names, aliases, integration platforms, device names, manufacturers, models/model IDs, areas and floors. Does not filter current entity state. Direct identity matches rank before inherited location matches; limit bounds records per page. If no substring matches, matchMode may label similar-name candidates; verify identity rather than treating similarity as an alias.'},domains:{type:'array',items:{type:'string'},maxItems:20},device_id:{type:'string'},area_id:{type:'string'},floor_id:{type:'string'},offset:{type:'integer',minimum:0},limit:{type:'integer',minimum:1,maximum:50}},required:['adapter'],additionalProperties:false},execute:async(input,context)=>new Promise((resolve,reject)=>{
   assertDiscoveryPermission(ctx,'inspect_resources',input,context).then(()=>{
   const child=spawn('/usr/bin/python3',['/home/somdutta/.config/opencode/mcp/resource_catalog.py'],{stdio:['pipe','pipe','pipe'],signal:context.signal});let out='';
   const timer=setTimeout(()=>child.kill('SIGKILL'),12000);child.stdin.end(JSON.stringify(input));
   child.stdout.on('data',d=>out+=d.toString());child.on('error',e=>{clearTimeout(timer);reject(e)});child.on('close',code=>{clearTimeout(timer);resolve({content:out||JSON.stringify({error:code===0?'No discovery output':'Discovery timed out or failed',read_only:true})})});
   }).catch(reject);
  })});
 });
 await ctx.session.hook('prompt',event=>{clearDiscovery(event.sessionID);clearCompletionCheck(event.sessionID);});
 await ctx.session.hook('context',event=>{
  if(event.model?.providerID==='evo-vision'){delete event.tools.discover_capabilities;delete event.tools.inspect_resources;return;}
  captureTools(event.sessionID,event.tools);

 });
}};
