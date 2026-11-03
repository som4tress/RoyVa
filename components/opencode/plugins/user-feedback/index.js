import {readFileSync} from 'node:fs';import {homedir} from 'node:os';
import {discardSession} from '../../lib/discard-session.mjs';
import {forgetSessionMemory} from '../../lib/session-lifecycle.mjs';
import {markDiscarded} from '/home/somdutta/Projects/agent-learning/src/discard.mjs';
import {parseFeedback,completedTarget,recordFeedback,status,receipt,HELP} from '/home/somdutta/Projects/agent-learning/src/feedback.mjs';
const quote=s=>"'"+s.replaceAll("'","'\\''")+"'";
export default {id:'user-feedback',async setup(ctx){
 const controller=new AbortController();
 void (async()=>{try{for await(const event of ctx.event.subscribe({types:['session.deleted'],signal:controller.signal})){
  const ids=new Set();const walk=v=>{if(!v||typeof v!=='object')return;for(const [k,x] of Object.entries(v)){if(['id','sessionID','session_id','sessionId'].includes(k)&&typeof x==='string'&&/^ses_[a-zA-Z0-9_-]+$/.test(x))ids.add(x);else if(x&&typeof x==='object')walk(x);}};walk(event);
  for(const id of ids)await forgetSessionMemory(id);
 }}catch(e){if(!controller.signal.aborted)console.error('Session cleanup event stream ended:',e.name);}})();
 await ctx.command.transform(editor=>editor.add({name:'feedback',description:'Accept an answer and authorize candidate tool creation, or reject/withdraw. No LLM call.',execute:async({sessionID,prompt})=>{
  const parsed=parseFeedback('/feedback '+(prompt.text||''));let text,discard=false;
  try{
   if(parsed.action==='help')text=HELP;
   else{
    const target=completedTarget(await ctx.session.context({sessionID}),sessionID,parsed.messageID);
    const s=parsed.action==='status'?status(target):recordFeedback({target,action:parsed.action,actor:'authenticated-opencode-user',source:'opencode-command',note:parsed.note});discard=parsed.action==='reject';text=discard?'Discarding this rejected session and its derived working memories. Start a fresh session after it closes.':receipt(parsed.action,s);
   }
  }catch(e){text=e.message;}
  if(discard)markDiscarded(sessionID);
  const service=JSON.parse(readFileSync(homedir()+'/.config/opencode/service.json','utf8'));
  const response=await fetch(`http://127.0.0.1:${service.port}/api/session/${encodeURIComponent(sessionID)}/shell`,{method:'POST',headers:{'content-type':'application/json',authorization:'Basic '+Buffer.from('opencode:'+service.password).toString('base64')},signal:AbortSignal.timeout(10000),body:JSON.stringify({command:"printf '%s\\n' "+quote(text)})});
  if(!response.ok)throw new Error('Feedback saved; confirmation could not be displayed. Use /feedback status.');
  // Finish command admission first; deleting its own running Session inline can
  // wait on the command itself. The shared gateway blocks the rejected ID.
  if(discard){const timer=setTimeout(()=>void discardSession(sessionID).catch(e=>console.error('Rejected session cleanup failed:',e.name)),150);timer.unref?.();}
 }}));
 return ()=>controller.abort();
}};
