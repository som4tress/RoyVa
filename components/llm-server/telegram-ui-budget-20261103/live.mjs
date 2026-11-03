import {readFileSync,writeFileSync} from 'node:fs';
const root='/home/somdutta/llm-server/telegram-ui-budget-20261103';
for(const n of ['api.env','opencode.env','ha.env'])for(const l of readFileSync('/home/somdutta/llm-server/'+n,'utf8').split('\n')){const i=l.indexOf('=');if(i>0)process.env[l.slice(0,i)]=l.slice(i+1).replace(/^["']|["']$/g,'');}
process.env.OPENCODE_TG_STATE_FILE=root+'/state.json';process.env.OPENCODE_TG_BIN='/home/somdutta/.opencode/bin/opencode';delete process.env.OPENCODE_TG_MODEL;
const {runTelegramSelfTest}=await import('/home/somdutta/.config/opencode/telegram/bridge.mjs');const reply=await runTelegramSelfTest(6064019420,'Read /proc/meminfo and report MemAvailable and SwapFree, clearly labelled in GiB. Do not modify anything.','Compact timeline and model label');writeFileSync(root+'/live-result.json',JSON.stringify(reply,null,2));console.log(JSON.stringify({ok:reply.ok,seconds:reply.seconds,text:reply.text}));if(!reply.ok)process.exitCode=1;
