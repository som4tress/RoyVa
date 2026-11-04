import {createHash} from 'node:crypto';
const hash=x=>createHash('sha256').update(x).digest('hex');
// Compatibility exports: active evidence is no longer excerpted or cached.
export const clearEvidenceMemo=()=>{};
export const boundedEvidence=original=>original;
export function cleanToolEvidence(body){
 const calls=new Map((body.messages||[]).flatMap(m=>m.tool_calls||[]).map(c=>[c.id,c.function||{}]));let seen=new Map(),changed=0,duplicates=0;
 const messages=(body.messages||[]).map(m=>{
  if(m.role==='user')seen=new Map();if(m.role!=='tool')return m;
  const arr=Array.isArray(m.content)&&m.content.every(p=>p.type==='text'&&Object.keys(p).every(k=>['type','text'].includes(k))),text=arr?m.content.map(p=>p.text).join('\n'):m.content;if(typeof text!=='string')return m;
  const tool=calls.get(m.tool_call_id)||{};if(!tool.name)return m;const key=hash(tool.name+'\n'+tool.arguments+'\n'+text);let content=text;
  if(text.length>1000&&seen.has(key)){content='[This tool call returned byte-identical evidence to earlier tool result '+seen.get(key)+', with identical tool arguments. That result, or its full-source reference, remains earlier in this request. This call already ran; do not replay it merely to obtain the duplicate text.]';duplicates++;}
  seen.set(key,m.tool_call_id);if(content===text)return m;changed++;return {...m,content:arr?[{type:'text',text:content}]:content};
 });return {body:changed?{...body,messages}:body,changed,archived:0,duplicates};
}
