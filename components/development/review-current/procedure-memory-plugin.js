import {rememberProcedure,procedureHint} from '../../lib/procedure-memory.mjs';
export default {
 id:'procedure-memory',
 async setup(ctx){
  const tasks=new Map();
  await ctx.session.hook('prompt',async event=>{
   let workspace=process.cwd();try{const session=await ctx.session.get({sessionID:event.sessionID});workspace=session.location?.directory||session.directory||workspace}catch{}
   tasks.set(event.sessionID,{text:event.prompt?.text||'',workspace,hasFiles:Boolean(event.prompt?.files?.length)});
   if(tasks.size>1000)tasks.delete(tasks.keys().next().value);
  });
  await ctx.session.hook('model.request',async event=>{
   const task=tasks.get(event.sessionID);if(!task||task.hasFiles)return;
   event.headers||={};
   if(event.headers['x-request-kind']==='ha'||event.headers['x-media-session'])return;
   const provider=event.model?.providerID;
   if(provider!=='openrouter'&&provider!=='evo-agent')return;
   event.baseURL='http://127.0.0.1:8011/'+(provider==='openrouter'?'generic-cloud':'generic-agent')+'/v1';
   event.headers['x-procedure-request-kind']=event.kind||'primary';
   event.headers['x-procedure-request-task']=encodeURIComponent(task.text);
  });
  await ctx.session.hook('context',async event=>{
   const task=tasks.get(event.sessionID);if(!task)return;
   const hint=procedureHint(task.text,event.sessionID,task.workspace);if(hint){event.system.push({type:'text',text:hint});console.log('[procedure-memory] recalled references for '+event.sessionID);}
  });
  await ctx.tool?.hook('execute.after',async event=>{
   if(event.status!=='completed')return;
   const task=tasks.get(event.sessionID);if(!task)return;
   try{rememberProcedure({task:task.text,workspace:task.workspace,tool:event.tool,args:event.input||{},result:event.result||{},sessionID:event.sessionID})}catch{}
  });
 }
};
