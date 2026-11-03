import fs from 'node:fs';import {DatabaseSync} from 'node:sqlite';
import {sanitizeContext,countInput} from '/home/somdutta/.config/opencode/lib/context-hygiene.mjs';
for(const line of fs.readFileSync('/home/somdutta/llm-server/api.env','utf8').split('\n')){const m=line.match(/^(?:export )?VLLM_API_KEY=(.*)$/);if(m)process.env.VLLM_API_KEY=m[1].replace(/^['"]|['"]$/g,'');}
const input=JSON.parse(fs.readFileSync('/home/somdutta/.local/share/opencode/cloud-context/payloads/029a5a0e-18be-48a0-ba2e-cda4790f57f9/original.json'));
const db=new DatabaseSync('/home/somdutta/.local/share/opencode/opencode.db',{readOnly:true});const d=JSON.parse(db.prepare('select data from session_message where id=?').get('msg_1a2e6c72b001mvH4kSMdJ1Uqa0').data);db.close();
const calls=d.content.filter(p=>p.type==='tool');
input.messages.push({role:'assistant',content:d.content.filter(p=>p.type==='text').map(p=>p.text).join('\n'),tool_calls:calls.map(p=>({id:p.id,type:'function',function:{name:p.name,arguments:JSON.stringify(p.state.input)}}))});
for(const p of calls)input.messages.push({role:'tool',tool_call_id:p.id,content:p.state.content.filter(x=>x.type==='text').map(x=>x.text).join('\n')});
const r=await sanitizeContext(input,{session:'ses_tg_6064019420_mvxqey2l',now:1793734400000});
const stats={...r.stats,toolCallsPreserved:r.body.messages.flatMap(m=>m.tool_calls||[]).length,toolResultsPreserved:r.body.messages.filter(m=>m.role==='tool').length};
fs.writeFileSync('/home/somdutta/llm-server/context-hygiene-20261103/distance-replay-result.json',JSON.stringify(stats,null,2));console.log(JSON.stringify(stats));
