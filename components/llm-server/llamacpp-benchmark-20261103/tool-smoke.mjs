import {runNativeText,openCodeAPI} from '/home/somdutta/.config/opencode/telegram/native-runner.mjs';
import {writeFileSync} from 'node:fs';
const sid='ses_llamacpp_tools_'+Date.now(),start=Date.now();
const r=await runNativeText(sid,'Call discover_capabilities exactly once to find web fetching capabilities. Do not fetch any pages or execute other tools. Report only the names returned by discovery.',{model:'evo-agent/qwen36-agent',timeout:120000});
const messages=await openCodeAPI('/api/session/'+sid+'/message');
writeFileSync(new URL('./tool-smoke.json',import.meta.url),JSON.stringify({sid,r,messages},null,2));
console.log(JSON.stringify({sid,ok:r.ok,seconds:(Date.now()-start)/1000,text:r.text,tools:messages.flatMap(m=>(m.content||[]).filter(p=>p.type==='tool').map(p=>({name:p.name,status:p.state?.status})))}));
