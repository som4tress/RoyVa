import {spawn} from 'node:child_process';
import {catalogPage,captureTools,clearDiscovery,DISCOVERY_RULE,EVIDENCE_RULE} from '../../lib/capability-discovery.mjs';
import {readCompletionCheck,clearCompletionCheck} from '../../lib/completion-check.mjs';
import {cloudModel} from '../../lib/routing-policy.mjs';
export default {id:'capability-discovery',async setup(ctx){
 await ctx.tool.transform(editor=>{
  editor.add({options:{codemode:false},name:'discover_capabilities',description:'Discover live registered tools, supported operations and exact input schemas. Use before capability refusals, API guesses or crossing a narrow task profile. Optionally enable named tools from the current agent context for the next step; this executes no operation and does not bypass permissions.',input:{type:'object',properties:{query:{type:'string',maxLength:200},names:{type:'array',items:{type:'string'},maxItems:10},enable:{type:'array',items:{type:'string'},maxItems:10},schemas:{type:'boolean'},offset:{type:'integer',minimum:0},limit:{type:'integer',minimum:1,maximum:30}},additionalProperties:false},execute:async(input,context)=>{
   const {selectCapabilities}=await import('../../lib/capability-discovery.mjs');
   const catalog=await ctx.tool.list();const snapshot=captureTools(context.sessionID,{});
   const page=catalogPage(catalog,{...input,available:Object.keys(snapshot.baseline)});
   const repair=readCompletionCheck(context.sessionID);
   if(repair){page.completionRecovery={reason:repair.reason,attempt:repair.attempts,policyInitiated:true,instruction:'The previous response did not complete the original request. Continue that existing request using supported tools, or ask a necessary clarification. Do not repeat completed actions.'};if(repair.route==='cloud')await ctx.session.switchModel({sessionID:context.sessionID,model:cloudModel()});}
   if(input.enable?.length)page.selection=selectCapabilities(context.sessionID,input.enable);
   return {content:JSON.stringify(page)};
  }});
  editor.add({options:{codemode:false},name:'inspect_resources',description:'Discover current resource names, stable IDs, state and relationships using a registered read-only adapter. Supports entities/devices/areas/floors with explicit scope and pagination. Use discovery rather than inventing aliases, assuming missing capabilities, or guessing ownership. No configuration or device changes.',input:{type:'object',properties:{adapter:{type:'string',enum:['home-assistant']},resource:{type:'string',enum:['entities','devices','areas','floors']},query:{type:'string',maxLength:200},domains:{type:'array',items:{type:'string'},maxItems:20},device_id:{type:'string'},area_id:{type:'string'},floor_id:{type:'string'},offset:{type:'integer',minimum:0},limit:{type:'integer',minimum:1,maximum:50}},required:['adapter'],additionalProperties:false},execute:async(input,context)=>new Promise((resolve,reject)=>{
   const child=spawn('/usr/bin/python3',['/home/somdutta/.config/opencode/mcp/resource_catalog.py'],{stdio:['pipe','pipe','pipe'],signal:context.signal});let out='';
   const timer=setTimeout(()=>child.kill('SIGKILL'),12000);child.stdin.end(JSON.stringify(input));
   child.stdout.on('data',d=>out+=d.toString());child.on('error',e=>{clearTimeout(timer);reject(e)});child.on('close',code=>{clearTimeout(timer);resolve({content:out||JSON.stringify({error:code===0?'No discovery output':'Discovery timed out or failed',read_only:true})})});
  })});
 });
 await ctx.session.hook('prompt',event=>{clearDiscovery(event.sessionID);clearCompletionCheck(event.sessionID);});
 await ctx.session.hook('context',event=>{
  if(event.model?.providerID==='evo-vision'){delete event.tools.discover_capabilities;delete event.tools.inspect_resources;return;}
  const s=captureTools(event.sessionID,event.tools);
  const names=Object.keys(s.baseline).filter(x=>!/^(home[-_]assistant_|ha[-_]history_)/.test(x));
  event.system.push({type:'text',text:DISCOVERY_RULE+' '+EVIDENCE_RULE+' General tools observed in this agent context: '+names.join(', ').slice(0,700)+'.'});
  const repair=readCompletionCheck(event.sessionID);
  if(repair)event.system.push({type:'text',text:'Completion check: the previous response was '+repair.reason+'. Continue the ORIGINAL task using the available capabilities and actual source evidence; a necessary clarification is valid. Retrieve missing task evidence before attributing results to a source. Do not repeat the question, invent a capability limit, or replay completed actions.'});
 });
 await ctx.session.hook('retry',event=>{if((readCompletionCheck(event.sessionID)?.attempts||0)>2)event.decision={retry:false};});
}};
