import {readFileSync,writeFileSync} from 'node:fs';import assert from 'node:assert/strict';
const root='/home/somdutta/llm-server/concise-output-20261103';
for(const name of ['api.env','opencode.env','ha.env'])for(const line of readFileSync('/home/somdutta/llm-server/'+name,'utf8').split('\n')){const i=line.indexOf('=');if(i>0)process.env[line.slice(0,i)]=line.slice(i+1).replace(/^["']|["']$/g,'');}
process.env.OPENCODE_TG_STATE_FILE=root+'/state.json';process.env.OPENCODE_TG_BIN='/home/somdutta/.opencode/bin/opencode';delete process.env.OPENCODE_TG_MODEL;
const {runTelegramSelfTest}=await import('/home/somdutta/.config/opencode/telegram/bridge.mjs');
const result=await runTelegramSelfTest(6064019420,'Summarize these project notes: Build passed at 09:10. Deployment request accepted at 09:12. Health check not yet run. Owner is Mira. Next check at 09:30. Completion is unverified.','Concise-output check');
const text=result.text.replace(/\n\nUsage[\s\S]*/,'');const words=text.trim().split(/\s+/).length;writeFileSync(root+'/result.json',JSON.stringify({...result,words},null,2));assert(result.ok);assert(words<=60);assert(/Mira/.test(text));assert(/09:30|9:30/.test(text));assert(/unverified|not.*(?:run|verified|confirmed)|pending|unconfirmed/i.test(text));
writeFileSync(root+'/result.json',JSON.stringify({...result,words},null,2));console.log(JSON.stringify({words,seconds:result.seconds,text}));
