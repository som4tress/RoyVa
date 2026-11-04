import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
const dir='/home/somdutta/llm-server/steering-removals-20261103';process.env.OPENCODE_TG_STATE_FILE=dir+'/telegram-state.json';
const env=Object.fromEntries(readFileSync('/home/somdutta/.config/opencode/telegram/bot.env','utf8').split('\n').filter(x=>x.includes('=')).map(x=>{const i=x.indexOf('=');return [x.slice(0,i).trim(),x.slice(i+1).trim().replace(/^["']|["']$/g,'')]}));
const chat=env.TELEGRAM_ALLOWED_USER_IDS.split(',')[0].trim();
const {runTelegramSelfTest}=await import('/home/somdutta/.config/opencode/telegram/bridge.mjs');
const {openCodeAPI}=await import('/home/somdutta/.config/opencode/telegram/native-runner.mjs');
for(let i=0;i<30;i++){try{await openCodeAPI('/api/session');break}catch{await new Promise(r=>setTimeout(r,1000))}}
const prompts=['show me all the entities that are on in my house today','show me all location histories for shobha in the past 5 days','What will be the weather for the next 7 days in Milpitas','What is the weather inside and outside my home','is ford off'];
const tracePath='/home/somdutta/.local/state/opencode/completion-check/trace-sessions.json';const old=existsSync(tracePath)?readFileSync(tracePath,'utf8'):null;mkdirSync('/home/somdutta/.local/state/opencode/completion-check',{recursive:true});let traces;try{traces=JSON.parse(old||'{}')}catch{traces={}};
const results=[];
try{for(let i=0;i<prompts.length;i++){
 let sid;console.log(JSON.stringify({event:'start',test:i+1}));
 const r=await runTelegramSelfTest(chat,prompts[i],'Steering removal '+(i+1)+'/5',{onSession:id=>{sid=id;writeFileSync(tracePath,JSON.stringify({...traces,sessions:[...(traces.sessions||[]),id]}),{mode:0o600})}});
 const messages=sid?await openCodeAPI('/api/session/'+sid+'/message'):[];
 results.push({test:i+1,prompt:prompts[i],sid,r,messages});writeFileSync(dir+'/results.json',JSON.stringify(results,null,2),{mode:0o600});
 console.log(JSON.stringify({event:'finish',test:i+1,ok:r.ok,seconds:r.seconds,sid,models:[...new Set(messages.filter(m=>m.type==='assistant').map(m=>m.model?.providerID+'/'+m.model?.id))],tools:messages.flatMap(m=>(m.content||[]).filter(p=>p.type==='tool').map(p=>({name:p.name,status:p.state?.status})))}));
}}finally{writeFileSync(tracePath,old||JSON.stringify({sessions:[]}),{mode:0o600})}
