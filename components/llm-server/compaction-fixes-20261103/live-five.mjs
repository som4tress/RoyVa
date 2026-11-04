import {runNativeText,openCodeAPI} from '/home/somdutta/.config/opencode/telegram/native-runner.mjs';import {writeFileSync} from 'node:fs';
const prompts=['show me all the entities that are on in my house today','show me all location histories for shobha in the past 5 days','What will be the weather for the next 7 days in Milpitas','What is the weather inside and outside my home','is ford off'];
const results=[];
for(let i=0;i<prompts.length;i++){
 const sid='ses_compaction_five_'+(i+1)+'_'+Date.now(),start=Date.now();console.log(JSON.stringify({event:'start',test:i+1,sid}));
 const r=await runNativeText(sid,prompts[i],{model:'evo-agent/qwen36-agent',timeout:240000});const messages=await openCodeAPI('/api/session/'+sid+'/message');
 const assistants=messages.filter(m=>m.type==='assistant'),tools=assistants.flatMap(m=>(m.content||[]).filter(p=>p.type==='tool').map(p=>({name:p.name,status:p.state?.status}))),models=[...new Set(assistants.map(m=>m.model?.providerID+'/'+m.model?.id))];
 results.push({test:i+1,prompt:prompts[i],sid,seconds:(Date.now()-start)/1000,r,messages});writeFileSync(new URL('./live-five-results.json',import.meta.url),JSON.stringify(results,null,2));
 console.log(JSON.stringify({event:'finish',test:i+1,ok:r.ok,seconds:results.at(-1).seconds,models,tools,outputChars:r.text?.length}));
}
