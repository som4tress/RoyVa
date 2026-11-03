import {readFileSync} from 'node:fs';import {homedir} from 'node:os';
export async function openCodeAPI(path,method='GET',body){
 const service=JSON.parse(readFileSync(homedir()+'/.config/opencode/service.json','utf8'));
 const response=await fetch(`http://127.0.0.1:${service.port}${path}`,{method:method.toUpperCase(),headers:{'content-type':'application/json',authorization:'Basic '+Buffer.from('opencode:'+service.password).toString('base64')},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(15000)});
 const raw=await response.text();let value;try{value=JSON.parse(raw)}catch{value=null;}
 if(!response.ok)throw Object.assign(new Error('OpenCode API request failed ('+response.status+').'),{status:response.status});
 return value?.data??value;
}
const words=parts=>(parts||[]).filter(p=>p.type==='text').map(p=>p.text||'').join('');
export async function runNativeText(sessionID,text,{model,agent='telegram',directory=homedir(),timeout=900000,onControl,onStarted,onActivity,isStopped,collectReferences=()=>[],api=openCodeAPI}={}){
 const path='/api/session/'+encodeURIComponent(sessionID),start=Date.now();let aborted=false,reason='',toolActivity=false,nextPermissionCheck=0,pendingApproval=null;
 const abort=async why=>{if(aborted)return;aborted=true;reason=why;try{await api(path+'/interrupt','POST',{})}catch{}};
 onControl?.(abort);
 try{
  try{await api(path)}catch(e){if(e.status!==404)throw e;const slash=model.indexOf('/');await api('/api/session','POST',{id:sessionID,agent,location:{directory},model:{providerID:model.slice(0,slash),id:model.slice(slash+1)}});}
  if(aborted||isStopped?.())return {ok:false,stopped:true,text:'Stopped.'};
  const slash=model.indexOf('/');await api(path+'/model','POST',{model:{providerID:model.slice(0,slash),id:model.slice(slash+1)}});
  await api(path+'/agent','POST',{agent});
  // Submit the exact user text as a JSON field. CLI positional serialization
  // must not turn it into a quoted data string.
  await api(path+'/prompt','POST',{text,delivery:'queue'});onStarted?.();
  while(!aborted&&Date.now()-start<timeout){
   const [messages,session]=await Promise.all([api(path+'/message'),api(path)]);
   const rows=(messages||[]).filter(m=>(m.time?.created||0)>=start).sort((a,b)=>a.time.created-b.time.created);
   const users=rows.filter(m=>m.type==='user'),assistants=rows.filter(m=>m.type==='assistant');
   const tools=assistants.flatMap(m=>(m.content||[]).filter(p=>p.type==='tool'));
   toolActivity=tools.length>0;
   if(Date.now()>=nextPermissionCheck){nextPermissionCheck=Date.now()+2000;try{const pending=await api(path+'/permission');pendingApproval=Array.isArray(pending)?pending[0]||null:null;}catch{}}
   const latestTool=tools.at(-1);
   if(pendingApproval)onActivity?.({tool:'permission',status:'approval-required',action:pendingApproval.action,at:Date.now()});
   else if(latestTool)onActivity?.({tool:latestTool.name,status:latestTool.state?.status||'running',at:Date.now()});
   const newestUser=users.at(-1),last=assistants.at(-1);
   const idle=newestUser&&(session.time?.idle||0)>=newestUser.time.created&&(session.time?.idle||0)>=(session.time?.busy||0);
   if(idle){
    const usageIds=assistants.map(m=>m.id);
    if(last?.error)return {ok:false,text:JSON.stringify(last.error),usageIds,toolActivity};
    const answer=last&&words(last.content);
    if(last?.time?.completed&&answer?.trim()&&!last.content?.some(p=>p.type==='tool')&&!['length','error'].includes(last.finish))return {ok:true,text:answer.trim(),assistantId:last.id,usageIds,references:collectReferences(tools),toolActivity};
    return {ok:false,text:'OpenCode finished without a confirmed answer.',usageIds,toolActivity};
   }
   await new Promise(r=>setTimeout(r,400));
  }
  if(!aborted)await abort('Processing time budget exceeded');
  return {ok:false,stopped:isStopped?.()||false,text:isStopped?.()?'Stopped.':reason||'Processing interrupted; completion unconfirmed.',toolActivity};
 }catch(e){return {ok:false,stopped:isStopped?.()||false,text:isStopped?.()?'Stopped.':e.message,toolActivity};}
}
