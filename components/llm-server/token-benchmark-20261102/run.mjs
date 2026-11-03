import {readFileSync,writeFileSync,existsSync} from 'node:fs';import {execFileSync} from 'node:child_process';
const root='/home/somdutta/llm-server/token-benchmark-20261102',phase=process.argv[2];
for(const n of ['api.env','opencode.env','ha.env'])for(const l of readFileSync('/home/somdutta/llm-server/'+n,'utf8').split('\n')){const i=l.indexOf('=');if(i>0)process.env[l.slice(0,i)]=l.slice(i+1).replace(/^["']|["']$/g,'');}
process.env.OPENCODE_TG_BIN='/home/somdutta/.opencode/bin/opencode';process.env.OPENCODE_TG_STATE_FILE=root+'/'+phase+'-state.json';process.env.OPENCODE_TG_TIMEOUT='300000';
const {runTelegramSelfTest,sendTelegramTestReport}=await import('/home/somdutta/.config/opencode/telegram/bridge.mjs');
const out=root+'/'+phase+'.json',results=existsSync(out)?JSON.parse(readFileSync(out)):[];
const selected=new Set((process.argv[3]||'1,2,3,4,5,6,7,8,9,10').split(',').map(Number));
for(const t of JSON.parse(readFileSync(root+'/workloads.json')).filter(t=>selected.has(t.id))){if(results.some(r=>r.id===t.id))continue;const start=Date.now();console.log(JSON.stringify({phase,id:t.id,name:t.name,event:'start'}));
const r=await runTelegramSelfTest(6064019420,'Use DeepSeek. '+t.prompt,`${phase} ${t.id} (targeted) — ${t.name}`);
let usage;try{usage=JSON.parse(execFileSync('python3',[root+'/usage.py',r.sessionId,String(start)],{encoding:'utf8'}))}catch(e){usage={error:String(e.message)}}
results.push({...t,...r,usage,startedAt:start});writeFileSync(out,JSON.stringify(results,null,2),{mode:0o600});console.log(JSON.stringify({phase,id:t.id,ok:r.ok,seconds:r.seconds,usage,preview:r.text.slice(0,180)}));
}
await sendTelegramTestReport(6064019420,`Token benchmark ${phase}: ${results.length}/${selected.size} finished. Detailed comparison follows after validation.`);
