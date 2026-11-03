import {readFileSync,writeFileSync} from 'node:fs';import {homedir} from 'node:os';import {createHash} from 'node:crypto';import assert from 'node:assert/strict';import {httpAsk} from './opencode_http_test.mjs';
const home=homedir();for(const name of ['api.env','opencode.env','ha.env'])for(const line of readFileSync(home+'/llm-server/'+name,'utf8').split('\n')){const at=line.indexOf('=');if(at>0)process.env[line.slice(0,at)]=line.slice(at+1).replace(/^"|"$/g,'');}
process.env.OPENCODE_TG_BIN=home+'/.opencode/bin/opencode';
process.env.OPENCODE_TG_STATE_FILE=home+'/llm-server/cache-stress-100/exact-request-telegram-state.json';
const {runOpenCode,sendTelegramTestReport,runTelegramSelfTest}=await import(home+'/.config/opencode/telegram/bridge.mjs');


const results=[];const prompts=['Living room status','Turn off sitting room lights','Living room status','Turn off sitting room light','Living room status','Turn off sitting room lights','Living room status','Turn off sitting room light'];
await sendTelegramTestReport(6064019420,'[Exact-request regression checks]\nRunning your exact room-status and singular/plural light commands through the Telegram handler. Each prompt and result will appear here. I will verify local/cloud providers from recorded traces. Only Sitting Room light-off commands are authorized in these checks.');
for(let i=0;i<prompts.length;i++){
 const reply=await runTelegramSelfTest(6064019420,prompts[i],'Exact request '+(i+1)+'/8',{compact:false});let providers=[];try{providers=JSON.parse(readFileSync(home+'/.local/share/opencode/task-learning/traces/'+createHash('sha256').update(reply.sessionId).digest('hex')+'.json','utf8')).providers||[]}catch{}
 const row={prompt:prompts[i],ok:reply.ok,seconds:reply.seconds,sessionId:reply.sessionId,providers,text:reply.text};results.push(row);writeFileSync(home+'/llm-server/cache-stress-100/exact-telegram-regression.json',JSON.stringify(results,null,2),{mode:0o600});console.log(JSON.stringify(row));await sendTelegramTestReport(6064019420,'[Trace '+(i+1)+'/8] '+providers.join(' → ')+' · '+reply.seconds.toFixed(1)+'s · '+(reply.ok?'completed':'failed'));
}
await sendTelegramTestReport(6064019420,'[Exact-request checks complete]\n'+results.filter(x=>x.ok).length+'/8 completed; '+results.filter(x=>x.providers.includes('openrouter')).length+' used OpenRouter. Full traces retained on EVO.');
