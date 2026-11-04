import {runNativeText,openCodeAPI} from '/home/somdutta/.config/opencode/telegram/native-runner.mjs';
import {writeFileSync} from 'node:fs';
const label=process.argv[2];const results=[];
const prompt='Do not use tools. Explain how a hash table handles collisions, resizing, and average versus worst-case lookup complexity. Write approximately 200 words, with one short concrete example.';
for(let i=0;i<2;i++){
 const sid='ses_llamacpp_'+label+'_'+Date.now();const start=Date.now();
 const r=await runNativeText(sid,prompt,{model:'evo-agent/qwen36-agent',timeout:180000});
 const msgs=await openCodeAPI('/api/session/'+sid+'/message');
 const result={sid,wallSeconds:(Date.now()-start)/1000,...r,messages:msgs};results.push(result);
 writeFileSync(new URL('./'+label+'.json',import.meta.url),JSON.stringify(results,null,2));
 console.log(JSON.stringify({label,trial:i+1,ok:r.ok,wallSeconds:result.wallSeconds,chars:r.text?.length,assistantMetadata:msgs.filter(m=>m.type==='assistant').map(({content,...m})=>m)}));
}
