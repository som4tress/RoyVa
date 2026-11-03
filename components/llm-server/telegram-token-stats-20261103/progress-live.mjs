import assert from 'node:assert/strict';import {readFileSync,writeFileSync} from 'node:fs';
const root='/home/somdutta/llm-server/telegram-token-stats-20261103';
for(const n of ['api.env','opencode.env','ha.env'])for(const l of readFileSync('/home/somdutta/llm-server/'+n,'utf8').split('\n')){const i=l.indexOf('=');if(i>0)process.env[l.slice(0,i)]=l.slice(i+1).replace(/^["']|["']$/g,'');}
delete process.env.OPENCODE_TG_MODEL;process.env.OPENCODE_TG_STATE_FILE=root+'/test-state.json';process.env.OPENCODE_TG_BIN='/home/somdutta/.opencode/bin/opencode';
const {runTelegramSelfTest}=await import('/home/somdutta/.config/opencode/telegram/bridge.mjs');
const samples=[];
const result=await runTelegramSelfTest(6064019420,'Read MemAvailable from /proc/meminfo using shell, then return that value and its unit. Do not change any files.','Token footer verification',{compact:false,onProgress:p=>samples.push(p)});
assert.equal(result.ok,true);assert.ok(!/Tokens \(local\):/.test(result.text));assert.ok(samples.some(p=>!p.finished&&p.delivered&&/current input/.test(p.text)));assert.ok(samples.some(p=>p.finished&&p.delivered&&/Tokens \(local\):/.test(p.text)));assert.ok(result.delivered?.length);
writeFileSync(root+'/progress-live-result.json',JSON.stringify({result,samples},null,2),{mode:0o600});console.log(JSON.stringify({ok:result.ok,text:result.text,delivered:result.delivered.length}));
