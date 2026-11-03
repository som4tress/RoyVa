import assert from 'node:assert/strict';import {readFileSync,writeFileSync} from 'node:fs';import {execFileSync} from 'node:child_process';
const root='/home/somdutta/llm-server/telegram-steering-20261103';
for(const n of ['api.env','opencode.env','ha.env'])for(const l of readFileSync('/home/somdutta/llm-server/'+n,'utf8').split('\n')){const i=l.indexOf('=');if(i>0)process.env[l.slice(0,i)]=l.slice(i+1).replace(/^["']|["']$/g,'');}
delete process.env.OPENCODE_TG_MODEL;process.env.OPENCODE_TG_STATE_FILE=root+'/openrouter-test-state.json';process.env.OPENCODE_TG_BIN='/home/somdutta/.opencode/bin/opencode';
const {runTelegramSelfTest,runTelegramControlSelfTest}=await import('/home/somdutta/.config/opencode/telegram/bridge.mjs');
const msg=text=>({message_id:Date.now(),chat:{id:6064019420,type:'private'},from:{id:6064019420},text});const delay=ms=>new Promise(r=>setTimeout(r,ms));
const probe=sid=>JSON.parse(execFileSync('python3',['-c',`import json,sqlite3,os,sys
c=sqlite3.connect('file:'+os.path.expanduser('~/.local/share/opencode/opencode.db')+'?mode=ro',uri=True)
rows=[json.loads(r[0]) for r in c.execute("select data from session_message where session_id=? and type='assistant' order by time_created",(sys.argv[1],))]
print(json.dumps([{'provider':d.get('model',{}).get('providerID'),'complete':bool(d.get('time',{}).get('completed'))} for d in rows]))`,sid],{encoding:'utf8'}));
const workload=JSON.parse(readFileSync('/home/somdutta/llm-server/clean-context-20261103/workloads.json')).find(x=>x.id===14).prompt;
const results=[];
for(const mode of ['steer','stop']){
 let sid,done=false;const started=Date.now();const task=runTelegramSelfTest(6064019420,workload,`OpenRouter ${mode} handoff check`,{onSession:s=>{sid=s}}).finally(()=>done=true);
 let evidence;
 for(let n=0;n<600&&!done;n++){if(sid){const rows=probe(sid);if(rows.some(r=>r.provider==='openrouter'&&!r.complete)){evidence=rows;break;}}await delay(200);}
 if(!evidence){const reply=await task;throw new Error('No active OpenRouter handoff observed; refusing to claim test coverage. '+JSON.stringify({sid,reply}));}
 console.log(JSON.stringify({event:'cloud-active',mode,sid,evidence,elapsedMs:Date.now()-started}));
 const controlAt=Date.now();await runTelegramControlSelfTest(msg(mode==='steer'?'/steer Cancel the investigation. No further tools. Reply only CLOUD_STEERING_WORKS.':'/stop'));
 const reply=await task;if(mode==='steer'){assert.equal(reply.ok,true);assert.match(reply.text,/CLOUD_STEERING_WORKS/);}else{assert.equal(reply.stopped,true);assert.deepEqual(reply.delivered,[]);}
 const item={mode,sid,evidence,controlToCompletionMs:Date.now()-controlAt,reply};results.push(item);writeFileSync(root+'/openrouter-results.json',JSON.stringify(results,null,2));console.log(JSON.stringify({event:'pass',mode,controlToCompletionMs:item.controlToCompletionMs,text:reply.text}));
}
