import {readFileSync,writeFileSync} from 'node:fs';import {homedir} from 'node:os';import {createHash} from 'node:crypto';import assert from 'node:assert/strict';import {httpAsk} from './opencode_http_test.mjs';
const home=homedir();for(const name of ['api.env','opencode.env','ha.env'])for(const line of readFileSync(home+'/llm-server/'+name,'utf8').split('\n')){const at=line.indexOf('=');if(at>0)process.env[line.slice(0,at)]=line.slice(at+1).replace(/^"|"$/g,'');}
process.env.OPENCODE_TG_BIN=home+'/.opencode/bin/opencode';
process.env.OPENCODE_TG_STATE_FILE=home+'/llm-server/cache-stress-100/confirmed-layout-test-state.json';
const {runOpenCode,sendTelegramTestReport,runTelegramSelfTest}=await import(home+'/.config/opencode/telegram/bridge.mjs');


const tests=[['Upstairs status',['Master Bedroom','Shivi Bedroom','Temple']],['Downstairs status',['Living Room','Kitchen','Hallway','Office','Sitting Room','Stairs']],['Temple status',['Area: Temple']],['Shivi Bedroom status',['Area: Shivi Bedroom']]];const results=[];
for(const[prompt,expected]of tests){const r=await runTelegramSelfTest(6064019420,prompt,'Confirmed floor layout — '+prompt,{compact:false});const missing=expected.filter(x=>!r.text.includes(x));results.push({prompt,missing,...r});writeFileSync(home+'/llm-server/cache-stress-100/confirmed-layout-telegram-tests.json',JSON.stringify(results,null,2),{mode:0o600});console.log(JSON.stringify({prompt,ok:r.ok,missing,seconds:r.seconds,session:r.sessionId,preview:r.text.slice(0,160)}));if(missing.length)break;}
