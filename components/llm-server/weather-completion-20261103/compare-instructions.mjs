import{readFileSync,writeFileSync}from'node:fs';
const root='/home/somdutta/llm-server/weather-completion-20261103';
const b=JSON.parse(readFileSync('/home/somdutta/.local/share/opencode/cloud-context/payloads/3f2b4f57-0354-4eb7-983d-7c9de63ab07f/modified.json','utf8'));
const env=readFileSync('/home/somdutta/llm-server/api.env','utf8');const key=env.split('\n').find(l=>l.startsWith('VLLM_API_KEY='))?.split('=').slice(1).join('=').replace(/^["']|["']$/g,'');
const minimal='Today is 2026-11-03. Timezone: America/Los_Angeles. You are a helpful assistant. Use the provided tools to obtain current factual information. Do not invent observations or attribute data to a source you have not accessed. Ask if required parameters are missing. Answer concisely, and distinguish missing coverage from verified results.';
const out=[];
for(const variant of ['observed','minimal']){
 const payload={...b,stream:false,temperature:0,seed:17,max_tokens:512,max_completion_tokens:512};delete payload.stream_options;
 if(variant==='minimal')payload.messages=b.messages.map(m=>m.role==='system'?{role:'system',content:minimal}:m);
 const started=Date.now();const response=await fetch('http://127.0.0.1:8000/v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+key},body:JSON.stringify(payload),signal:AbortSignal.timeout(90000)});const data=await response.json();
 const r={variant,status:response.status,seconds:(Date.now()-started)/1000,usage:data.usage,answer:data.choices?.[0]?.message,finish:data.choices?.[0]?.finish_reason,error:response.ok?undefined:data.error?.message};out.push(r);writeFileSync(root+'/instruction-comparison.json',JSON.stringify(out,null,2),{mode:0o600});console.log(JSON.stringify(r));
}
