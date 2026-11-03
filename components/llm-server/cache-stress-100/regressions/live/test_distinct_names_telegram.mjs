import {readFileSync,writeFileSync} from 'node:fs';import {homedir} from 'node:os';import {createHash} from 'node:crypto';import assert from 'node:assert/strict';import {httpAsk} from './opencode_http_test.mjs';
const home=homedir();for(const name of ['api.env','opencode.env','ha.env'])for(const line of readFileSync(home+'/llm-server/'+name,'utf8').split('\n')){const at=line.indexOf('=');if(at>0)process.env[line.slice(0,at)]=line.slice(at+1).replace(/^"|"$/g,'');}
process.env.OPENCODE_TG_BIN=home+'/.opencode/bin/opencode';
process.env.OPENCODE_TG_STATE_FILE=home+'/llm-server/cache-stress-100/distinct-name-check-state.json';
const {runOpenCode,sendTelegramTestReport,runTelegramSelfTest}=await import(home+'/.config/opencode/telegram/bridge.mjs');


const results=[];for(const prompt of ['Downstairs Common Area status','Downstairs Thermostat status','List all downstairs lights']){const r=await runTelegramSelfTest(6064019420,prompt,'Distinct names — '+prompt,{compact:false});const row={prompt,...r};results.push(row);writeFileSync(home+'/llm-server/cache-stress-100/distinct-name-live-verification.json',JSON.stringify(results,null,2),{mode:0o600});console.log(JSON.stringify({prompt,ok:r.ok,seconds:r.seconds,session:r.sessionId,text:r.text.slice(0,240)}));}
