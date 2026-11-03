export const REPORT_TOOL='ha-history_get_device_status_report';
export function isStatusReport(text){
 const s=text.toLowerCase().replace(/[.!?;]?\s*(?:do not change anything|make no changes|read[ -]only)[.!?]*$/,'').trim();
 if(/\b(home|house|household)\b/.test(s.replace(/\bhome\s*assistant\b/g,''))&&/\b(status|states?|overview|inventory)\b/.test(s)&&!/\b(turn|set|change|why|history|yesterday|news|stock|price|sale|market)\b/.test(s))return true;
 return /\b(lights?|devices?|switch(?:es)?|fans?|entities|sensors?|thermostats?|climate|locks?|covers?|speakers?)\b/.test(s)&&/\b(status|states?|show|list|display|which|what)\b/.test(s)&&(/\b(table|tabular|inventory|report)\b/.test(s)||/\b(lights|devices|switches|fans|entities|sensors)\b/.test(s)||/\b(all|every)\b/.test(s)&&/\b(lights?|devices?|switches|fans?|entities|sensors?)\b/.test(s))&&!/\b(turn|toggle|set|dim|change|enable|disable|activate|deactivate|run|start|stop|why|who|how|cause|caused|turned|history|yesterday|before|after|compare|since|past|last|ago|earlier|when|explain)\b/.test(s);
}
function decode(content,depth=0){
 if(depth>5)return null;
 if(typeof content==='string'){try{return decode(JSON.parse(content),depth+1)}catch{return null}}
 if(Array.isArray(content)){
  for(const part of content){const found=decode(part?.text??part,depth+1);if(found)return found;}return null;
 }
 if(!content||typeof content!=='object')return null;
 if(content.isError)return null;
 if(content.kind==='ha_status_report')return content;
 return content.content?decode(content.content,depth+1):null;
}
const cell=x=>String(x).replace(/[\r\n\t]+/g,' ').replace(/\|/g,'\\|').replace(/[\u0000-\u001f]/g,' ').slice(0,200);
export function renderReport(report){
 if(report?.kind!=='ha_status_report'||report.version!==1||report.read_only!==true||!Array.isArray(report.rows)||report.rows.length>200||!Array.isArray(report.domains)||!report.domains.every(d=>typeof d==='string')||!Number.isInteger(report.total)||report.total<report.rows.length)return null;
 if(![JSON.stringify(['Device','Type','State']),JSON.stringify(['Device','Type','State','Area'])].includes(JSON.stringify(report.columns))||!report.rows.every(r=>Array.isArray(r)&&r.length===report.columns.length&&r.every(v=>typeof v==='string')))return null;
 const title=`Live Home Assistant status (${report.rows.length} of ${report.total})`;
 const filters=report.filters||{};
 const scope='Scope: '+report.domains.map(cell).join(', ')+(filters.name?' • Name: '+cell(filters.name):'')+(filters.state?' • State: '+cell(filters.state):'')+(Array.isArray(filters.states)&&filters.states.length?' • States: '+filters.states.map(cell).join(' or '):'')+(filters.area?' • Area: '+cell(filters.area):'')+(filters.floor?' • Floor: '+cell(filters.floor):'');
 if(!report.rows.length)return `${title}\n${scope}\n\nNo devices matched the requested filters.`;
 const table=['| '+report.columns.map(cell).join(' | ')+' |','|'+report.columns.map(()=>'---').join('|')+'|',...report.rows.map(r=>'| '+r.map(cell).join(' | ')+' |')].join('\n');
 return title+'\n'+scope+'\n\n'+table+(report.truncated?'\n\nReport truncated; narrow the filters to view the remaining devices.':'');
}
export function reportFromRequest(body){
 const msgs=body.messages||[];const last=msgs.at(-1);
 if(last?.role!=='tool'||!last.tool_call_id)return null;
 const assistant=[...msgs].reverse().find(m=>m.role==='assistant'&&m.tool_calls?.some(c=>c.id===last.tool_call_id));
 const call=assistant?.tool_calls?.find(c=>c.id===last.tool_call_id);
 if(call?.function?.name!==REPORT_TOOL||assistant.tool_calls.some(c=>c.function?.name!==REPORT_TOOL))return null;
 const index=msgs.indexOf(assistant);
 if(msgs.slice(index+1).some(m=>m.role!=='tool'))return null;
 const answers=assistant.tool_calls.map(c=>msgs.slice(index+1).find(m=>m.role==='tool'&&m.tool_call_id===c.id));
 if(answers.some(a=>!a))return null;
 const reports=answers.map(a=>decode(a.content));if(reports.some(r=>!r||!renderReport(r)))return null;
 if(reports.length===1)return renderReport(reports[0]);
 if(reports.some(r=>JSON.stringify(r.columns)!==JSON.stringify(reports[0].columns)||r.filters?.area!==reports[0].filters?.area||r.filters?.floor!==reports[0].filters?.floor))return reports.map(renderReport).join('\n\n');
 const rows=[...new Map(reports.flatMap(r=>r.rows).map(r=>[r[0]+'|'+r[1],r])).values()];
 if(rows.length>200)return null;
 const stateLists=reports.map(r=>r.filters?.states||(r.filters?.state?[r.filters.state]:null));
 const filters={...reports[0].filters,state:null,states:stateLists.every(Boolean)?[...new Set(stateLists.flat())]:null};
 return renderReport({...reports[0],filters,rows,total:reports.every(r=>!r.truncated)?rows.length:Math.max(rows.length,reports.reduce((n,r)=>n+r.total,0)),domains:[...new Set(reports.flatMap(r=>r.domains))],truncated:reports.some(r=>r.truncated)});
}
export function reportWire(body,text){
 const id='chatcmpl-ha-report-'+Date.now();const created=Math.floor(Date.now()/1000);const base={id,created,model:body.model};
 if(!body.stream)return {type:'application/json',body:JSON.stringify({...base,object:'chat.completion',choices:[{index:0,message:{role:'assistant',content:text},finish_reason:'stop'}],usage:{prompt_tokens:0,completion_tokens:0,total_tokens:0}})};
 const chunk=delta=>({...base,object:'chat.completion.chunk',choices:[{index:0,delta,finish_reason:null}]});
 return {type:'text/event-stream',body:'data: '+JSON.stringify(chunk({role:'assistant',content:text}))+'\n\n'+'data: '+JSON.stringify({...base,object:'chat.completion.chunk',choices:[{index:0,delta:{},finish_reason:'stop'}]})+'\n\n'+'data: [DONE]\n\n'};
}
