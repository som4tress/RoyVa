import {readFileSync,writeFileSync} from 'node:fs';import {execFileSync} from 'node:child_process';
const root='/home/somdutta/llm-server/weather-completion-20261103';
for(const n of ['api.env','opencode.env','ha.env'])for(const l of readFileSync('/home/somdutta/llm-server/'+n,'utf8').split('\n')){const i=l.indexOf('=');if(i>0)process.env[l.slice(0,i)]=l.slice(i+1).replace(/^["']|["']$/g,'');}
delete process.env.OPENCODE_TG_MODEL;process.env.OPENCODE_TG_STATE_FILE=root+'/focused-state.json';process.env.OPENCODE_TG_BIN='/home/somdutta/.opencode/bin/opencode';process.env.OPENCODE_TG_TIMEOUT='300000';
const {runTelegramSelfTest}=await import('/home/somdutta/.config/opencode/telegram/bridge.mjs');
const {runTelegramControlSelfTest,sendTelegramTestReport}=await import('/home/somdutta/.config/opencode/telegram/bridge.mjs');
const prompt='Milpitas, California. Please check the forecast through 21 November and clearly say how far the source actually covers.';
await sendTelegramTestReport(6064019420,'[Weather discovery follow-up]\n'+prompt);
const start=Date.now();const reply=await runTelegramControlSelfTest({message_id:Date.now(),date:Math.floor(Date.now()/1000),chat:{id:6064019420,type:'private'},from:{id:6064019420,is_bot:false},text:prompt});
writeFileSync(root+'/weather-followup-result.json',JSON.stringify({...reply,seconds:(Date.now()-start)/1000},null,2),{mode:0o600});console.log(JSON.stringify({...reply,seconds:(Date.now()-start)/1000}));
