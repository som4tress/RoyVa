import {readFileSync,writeFileSync} from 'node:fs';import {homedir} from 'node:os';import {createHash} from 'node:crypto';import assert from 'node:assert/strict';import {httpAsk} from './opencode_http_test.mjs';
const home=homedir();for(const name of ['api.env','opencode.env','ha.env'])for(const line of readFileSync(home+'/llm-server/'+name,'utf8').split('\n')){const at=line.indexOf('=');if(at>0)process.env[line.slice(0,at)]=line.slice(at+1).replace(/^"|"$/g,'');}
process.env.OPENCODE_TG_BIN=home+'/.opencode/bin/opencode';
process.env.OPENCODE_TG_STATE_FILE=home+'/llm-server/cache-stress-100/handoff-timer-proof-state.json';
const {runOpenCode,sendTelegramTestReport,runTelegramSelfTest}=await import(home+'/.config/opencode/telegram/bridge.mjs');


const prompt='Measure current loopback packet loss with ping -c 34 -i 1 127.0.0.1. Run the measurement now exactly once and report its fresh packet counts and loss; do not reuse a previous measurement. Only localhost; no file or setting changes.';
const reply=await runTelegramSelfTest(6064019420,prompt,'Controlled 30-second local-to-cloud handoff',{compact:false});writeFileSync(home+'/llm-server/cache-stress-100/live-tool-handoff-proof.json',JSON.stringify(reply,null,2),{mode:0o600});console.log(JSON.stringify(reply));
