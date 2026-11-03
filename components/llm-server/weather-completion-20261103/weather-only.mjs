import {readFileSync,writeFileSync} from 'node:fs';import {execFileSync} from 'node:child_process';
const root='/home/somdutta/llm-server/weather-completion-20261103';
for(const n of ['api.env','opencode.env','ha.env'])for(const l of readFileSync('/home/somdutta/llm-server/'+n,'utf8').split('\n')){const i=l.indexOf('=');if(i>0)process.env[l.slice(0,i)]=l.slice(i+1).replace(/^["']|["']$/g,'');}
delete process.env.OPENCODE_TG_MODEL;process.env.OPENCODE_TG_STATE_FILE=root+'/focused-state.json';process.env.OPENCODE_TG_BIN='/home/somdutta/.opencode/bin/opencode';process.env.OPENCODE_TG_TIMEOUT='300000';
const {runTelegramSelfTest}=await import('/home/somdutta/.config/opencode/telegram/bridge.mjs');
const cases=[{id:'weather',prompt:'What does the weather look like till 21 Nov?'}];
const results=[];
for(const t of cases){console.log(JSON.stringify({event:'start',id:t.id}));const reply=await runTelegramSelfTest(6064019420,t.prompt,'Focused capability discovery — '+t.id,{onSession:s=>{writeFileSync(root+'/active.json',JSON.stringify({id:t.id,session:s,at:Date.now()}));writeFileSync('/home/somdutta/.local/state/opencode/completion-check/trace-sessions.json',JSON.stringify({sessions:[s]}),{mode:0o600});}});results.push({...t,...reply});writeFileSync(root+'/focused-results.json',JSON.stringify(results,null,2),{mode:0o600});console.log(JSON.stringify({event:'done',id:t.id,ok:reply.ok,seconds:reply.seconds,text:reply.text}));}
