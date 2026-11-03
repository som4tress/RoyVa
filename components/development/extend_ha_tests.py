from pathlib import Path
p=Path('/tmp/ha_speed_test.mjs');s=p.read_text().replace('assert.equal(b.tool_choice.function.name,read);',"assert.equal(b.tool_choice,'required');")
s+='''
const makeRequest=(id,body,kind='primary')=>({sessionID:id,kind,model:{providerID:'evo-agent',id:'qwen36-agent'},request:new Request('http://localhost/test',{method:'POST',body:JSON.stringify(body)})});
let w=makeRequest('action-speed-test',{messages:[{role:'system',content:'Large irrelevant context'},{role:'user',content:'Turn on the kitchen light'}],tools:[{type:'function',function:{name:write}},{type:'function',function:{name:'shell'}}],chat_template_kwargs:{enable_thinking:true}});
await hooks['http.request'](w);let wb=await w.request.json();assert.equal(wb.chat_template_kwargs.enable_thinking,false);assert(wb.tools.some(t=>t.function.name===write));assert(!wb.tools.some(t=>t.function.name==='shell'));assert(!JSON.stringify(wb.messages).includes('Large irrelevant context'));assert(JSON.stringify(wb.messages).includes('Never turn off computers'));
await hooks.prompt({sessionID:'history-speed-test',prompt:{text:'Which recorded locations did Somdutta visit today?'}});
await hooks.context({sessionID:'history-speed-test',model:{providerID:'evo-agent',id:'qwen36-agent'},system:[],options:{},tools:{'ha-history_get_visited_locations':{},[write]:{}}});
let q=makeRequest('history-speed-test',{messages:[{role:'user',content:'Which recorded locations did Somdutta visit today?'}],tools:[{type:'function',function:{name:'ha-history_get_visited_locations'}},{type:'function',function:{name:write}}]});
await hooks['http.request'](q);let qb=await q.request.json();assert.equal(qb.chat_template_kwargs.enable_thinking,false);assert.deepEqual(qb.tools.map(t=>t.function.name),['ha-history_get_visited_locations']);assert.equal(qb.tool_choice,'required');
let aux=makeRequest('history-speed-test',{messages:[],max_tokens:8192,chat_template_kwargs:{enable_thinking:true}},'title');await hooks['http.request'](aux);const ab=await aux.request.json();assert.equal(ab.max_tokens,128);assert.equal(ab.chat_template_kwargs.enable_thinking,false);
console.log('PASS: compact write/history paths, relevant tools, computer safeguards, generic household history and bounded HA auxiliary requests.');
'''
p.write_text(s)
