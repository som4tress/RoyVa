import fs from 'node:fs';
import {sanitizeContext,countInput} from '/home/somdutta/.config/opencode/lib/context-hygiene.mjs';
for(const line of fs.readFileSync('/home/somdutta/llm-server/api.env','utf8').split('\n')){const m=line.match(/^(?:export )?VLLM_API_KEY=(.*)$/);if(m)process.env.VLLM_API_KEY=m[1].replace(/^['"]|['"]$/g,'');}
const root='/home/somdutta/llm-server/context-hygiene-20261103';
const original=JSON.parse(fs.readFileSync('/home/somdutta/.local/share/opencode/cloud-context/payloads/8ccd9e4c-b02f-45e0-92e9-9877224426b9/modified.json'));
const before=await countInput(original);
const {body,stats}=await sanitizeContext(original,{session:'ses_tg_6064019420_mvxqey2l',now:1793732540776});
const result={beforeTokens:before,...stats,afterMessageCount:body.messages.length,roles:body.messages.map(m=>m.role),historicalToolResults:body.messages.filter(m=>m.role==='tool').length,tools:body.tools?.length};
fs.writeFileSync(root+'/replay-result.json',JSON.stringify(result,null,2));
console.log(JSON.stringify(result));
