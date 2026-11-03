import {mkdirSync,writeFileSync,appendFileSync} from 'node:fs';import {homedir} from 'node:os';import {randomUUID} from 'node:crypto';
export const payloadRoot=homedir()+'/.local/share/opencode/cloud-context/payloads';
function redact(v,key=''){
 if(typeof v==='string'){
  if(/^(authorization|password|api[_-]?key|ha_token|access_token|secret)$/i.test(key))return '[REDACTED]';
  return v.replace(/Bearer\s+[A-Za-z0-9._-]{16,}/gi,'Bearer [REDACTED]').replace(/\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/g,'[REDACTED JWT]').replace(/\bsk-(?:or-v1-)?[A-Za-z0-9_-]{20,}\b/g,'[REDACTED API KEY]').replace(/((?:access_token|api_key|password)=)[^\s&"']+/gi,'$1[REDACTED]');
 }
 if(Array.isArray(v))return v.map(x=>redact(x));
 if(v&&typeof v==='object')return Object.fromEntries(Object.entries(v).map(([k,x])=>[k,redact(x,k)]));return v;
}
export function snapshotCloudRequest(original,modified,{session,kind}={}){
 const id=randomUUID(),dir=payloadRoot+'/'+id;mkdirSync(dir,{recursive:true,mode:0o700});
 const before=JSON.stringify(original),after=JSON.stringify(modified),a=Buffer.byteLength(before),b=Buffer.byteLength(after);
 const changes=(original.messages||[]).flatMap((m,i)=>JSON.stringify(m)===JSON.stringify(modified.messages?.[i])?[]:[{message:i,role:m.role,tool_call_id:m.tool_call_id,originalBytes:Buffer.byteLength(JSON.stringify(m)),modifiedBytes:Buffer.byteLength(JSON.stringify(modified.messages?.[i]||null))}]);
 const meta={id,session,kind,at:new Date().toISOString(),originalBytes:a,modifiedBytes:b,savedBytes:a-b,savedPercent:a?100*(a-b)/a:0,unchanged:before===after,changes,redactedReviewCopies:true,originalTokenCount:null,originalTokenNote:'Not measured with the DeepSeek tokenizer. Byte reduction is exact; token reduction is not inferred from bytes.'};
 for(const[name,v]of [['original.json',redact(original)],['modified.json',redact(modified)],['comparison.json',meta]])writeFileSync(dir+'/'+name,JSON.stringify(v,null,2),{mode:0o600});
 appendFileSync(payloadRoot+'/index.jsonl',JSON.stringify(meta)+'\n',{mode:0o600});return {id,dir};
}
export function snapshotCloudResponse(snapshot,wire,status){
 if(!snapshot)return;const meta={status};
 const take=j=>{if(j.id)meta.generationID=j.id;if(j.model)meta.model=j.model;if(j.provider)meta.provider=j.provider;if(j.usage)meta.usage=j.usage;const c=j.choices?.[0];if(c?.finish_reason)meta.finishReason=c.finish_reason;};
 try{take(JSON.parse(wire))}catch{for(const l of wire.split('\n'))if(l.startsWith('data: ')){try{take(JSON.parse(l.slice(6)))}catch{}}}
 writeFileSync(snapshot.dir+'/response-usage.json',JSON.stringify(meta,null,2),{mode:0o600});
}
