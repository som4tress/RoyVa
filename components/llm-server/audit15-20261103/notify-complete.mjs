import {readFileSync} from 'node:fs';
for(const n of ['api.env','opencode.env','ha.env'])for(const l of readFileSync('/home/somdutta/llm-server/'+n,'utf8').split('\n')){const i=l.indexOf('=');if(i>0)process.env[l.slice(0,i)]=l.slice(i+1).replace(/^["']|["']$/g,'');}
process.env.OPENCODE_TG_STATE_FILE='/home/somdutta/llm-server/audit15-20261103/state.json';
const {sendTelegramTestReport}=await import('/home/somdutta/.config/opencode/telegram/bridge.mjs');
await sendTelegramTestReport(6064019420,'Audit complete: all 15 queries produced replies, but several have accuracy or workflow bugs. Recorded cloud cost: $0.0825. No implementation files or fixtures changed. The Test / Bug / Proposal table, including whether local work helped each handoff, is in the Codex chat. No fixes applied.');
