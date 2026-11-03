import {readFileSync,writeFileSync} from 'node:fs';import {execFileSync} from 'node:child_process';
const root='/home/somdutta/llm-server/audit15-20261103';
for(const n of ['api.env','opencode.env','ha.env'])for(const l of readFileSync('/home/somdutta/llm-server/'+n,'utf8').split('\n')){const i=l.indexOf('=');if(i>0)process.env[l.slice(0,i)]=l.slice(i+1).replace(/^["']|["']$/g,'');}
delete process.env.OPENCODE_TG_MODEL;process.env.OPENCODE_TG_BIN='/home/somdutta/.opencode/bin/opencode';process.env.OPENCODE_TG_STATE_FILE=root+'/state.json';process.env.OPENCODE_TG_TIMEOUT='300000';process.env.OPENCODE_TG_AGENT='telegram';process.env.OPENCODE_TG_DIR='/home/somdutta';
const {runTelegramControlSelfTest,sendTelegramTestReport}=await import('/home/somdutta/.config/opencode/telegram/bridge.mjs');
const results=[];const tests=JSON.parse(readFileSync(root+'/workloads.json'));const chat=6064019420;
await sendTelegramTestReport(chat,'Read-only audit: repeating the original 15 queries in order. No implementation changes or tool approvals. General queries share a diagnostic conversation; HA routing uses its normal session handling.');
for(const t of tests){
 await sendTelegramTestReport(chat,`Audit ${t.id}/15 — ${t.name}\n${t.prompt}`);
 const startedAt=Date.now();let sessionId=null;const progress=[];let reply;
 console.log(JSON.stringify({event:'start',id:t.id,name:t.name}));
 try{reply=await runTelegramControlSelfTest({message_id:Date.now(),date:Math.floor(Date.now()/1000),chat:{id:chat,type:'private'},from:{id:chat,is_bot:false},text:t.prompt},{onSession:s=>sessionId=s,onProgress:p=>progress.push({...p,at:Date.now()})});}
 catch(e){reply={ok:false,text:'Audit harness caught '+e.name+': '+e.message};}
 let usage=null;
 if(sessionId)try{usage=JSON.parse(execFileSync('python3',['/home/somdutta/.config/opencode/scripts/openrouter-usage','--session',sessionId,'--since-ms',String(startedAt),'--until-ms',String(Date.now()),'--all-providers','--json'],{encoding:'utf8',timeout:12000}));}catch(e){usage={error:e.name};}
 const result={id:t.id,name:t.name,prompt:t.prompt,sessionId,startedAt,seconds:(Date.now()-startedAt)/1000,reply,usage,progress};results.push(result);
 writeFileSync(root+'/results.json',JSON.stringify(results,null,2),{mode:0o600});writeFileSync(root+'/status.json',JSON.stringify({finished:t.id,total:15,at:Date.now()}),{mode:0o600});
 console.log(JSON.stringify({event:'done',id:t.id,ok:reply.ok,seconds:result.seconds,text:reply.text}));
 await sendTelegramTestReport(chat,`Audit ${t.id}/15 recorded: ${result.seconds.toFixed(1)}s. ${reply.ok?'Response received; factual review pending.':'Incomplete/error; logged for review.'} No fixes applied.`);
}
console.log('ALL_15_RECORDED');
