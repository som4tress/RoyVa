import {readFileSync,writeFileSync} from 'node:fs';import {homedir} from 'node:os';import {createHash} from 'node:crypto';import assert from 'node:assert/strict';import {httpAsk} from './opencode_http_test.mjs';
const home=homedir();for(const name of ['api.env','opencode.env','ha.env'])for(const line of readFileSync(home+'/llm-server/'+name,'utf8').split('\n')){const at=line.indexOf('=');if(at>0)process.env[line.slice(0,at)]=line.slice(at+1).replace(/^"|"$/g,'');}
process.env.OPENCODE_TG_BIN=home+'/.opencode/bin/opencode';
process.env.OPENCODE_TG_STATE_FILE=home+'/llm-server/cache-stress-100/scope-regression-state.json';
const {runOpenCode,sendTelegramTestReport,runTelegramSelfTest}=await import(home+'/.config/opencode/telegram/bridge.mjs');


const results=[];for(const [i,prompt]of ['Downstairs status','Downstairs status','Living room status','List all downstairs lights'].entries()){
 const reply=await runTelegramSelfTest(6064019420,prompt,'Floor/area coverage '+(i+1)+'/4',{compact:false});const expected=prompt==='Living room status'?['Living Room Dimmer','Island Dimmer','NT50W','Media Wall Side Lights']:['Living Room Dimmer','Kitchen Dimmer','Island Dimmer','NT50W','Media Wall Side Lights'];const missing=expected.filter(n=>!reply.text.includes(n));const row={prompt,missing,...reply};results.push(row);writeFileSync(home+'/llm-server/cache-stress-100/floor-scope-live-regression.json',JSON.stringify(results,null,2),{mode:0o600});console.log(JSON.stringify({prompt,ok:reply.ok,seconds:reply.seconds,sessionId:reply.sessionId,missing,text:reply.text.slice(0,180)}));await sendTelegramTestReport(6064019420,'[Coverage check] '+(reply.ok&&!missing.length?'PASS':'FAIL')+' · '+reply.seconds.toFixed(1)+'s'+(missing.length?' · missing: '+missing.join(', '):' · requested lights present'));if(missing.length)break;
}
