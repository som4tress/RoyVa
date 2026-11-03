import assert from 'node:assert/strict';import {readFileSync,writeFileSync} from 'node:fs';
const root='/home/somdutta/llm-server/telegram-token-stats-20261103';
for(const n of ['api.env','opencode.env','ha.env'])for(const l of readFileSync('/home/somdutta/llm-server/'+n,'utf8').split('\n')){const i=l.indexOf('=');if(i>0)process.env[l.slice(0,i)]=l.slice(i+1).replace(/^["']|["']$/g,'');}
delete process.env.OPENCODE_TG_MODEL;process.env.OPENCODE_TG_STATE_FILE=root+'/test-state.json';process.env.OPENCODE_TG_BIN='/home/somdutta/.opencode/bin/opencode';
const {runTelegramSelfTest}=await import('/home/somdutta/.config/opencode/telegram/bridge.mjs');
const result=await runTelegramSelfTest(6064019420,'Reply exactly: Token stats working. Do not call tools.','Token footer verification',{compact:false});
assert.equal(result.ok,true);assert.match(result.text,/Tokens \(local\):/);assert.match(result.text,/peak/);assert.ok(result.delivered?.length);
writeFileSync(root+'/live-result.json',JSON.stringify(result,null,2),{mode:0o600});console.log(JSON.stringify({ok:result.ok,text:result.text,delivered:result.delivered.length}));
