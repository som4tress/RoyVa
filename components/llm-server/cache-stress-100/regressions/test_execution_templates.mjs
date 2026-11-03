import assert from 'node:assert/strict';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';import {tmpdir} from 'node:os';import {join} from 'node:path';
import {queryKey,saveTemplate,findTemplate,currentTurn,candidateFromTurn,tryExecutionTemplate,learnExecutionTemplate,formatProcedure} from '/home/somdutta/.config/opencode/lib/execution-templates.mjs';
const dir=mkdtempSync(join(tmpdir(),'execution-template-test-')),path=join(dir,'templates.json'),code='codeA',now=Date.now();
const query='What is Hall Lamp status?',tool='ha-history_get_device_status',recipe={kind:'read',tool,args:{name:'Hall Lamp'},expected_entities:['light.hall_lamp'],query};
const data={read_only:true,count:1,matches:[{name:'Hall Lamp',entity_id:'light.hall_lamp',domain:'light',state:'off'}]};
try{
 assert.equal(queryKey(query),queryKey(' WHAT is Hall Lamp status! '));assert.notEqual(queryKey('Turn Hall Lamp off'),queryKey('Turn Hall Lamp on'));
 assert(saveTemplate(query,recipe,{path,code,now}));assert(findTemplate(query,{path,code,now}));assert(!findTemplate(query,{path,code:'changed',now}));assert(!findTemplate(query,{path,code,now:now+31*86400000}));
 let calls=0;const body={messages:[{role:'user',content:query}]};const runner=async req=>{calls++;assert.equal(req.operation,'execute');return {ok:true,data}};
 const reply=await tryExecutionTemplate(body,{run:runner,path,code,now});assert.equal(reply.text,'Hall Lamp: off.');assert.equal(reply.zeroLLM,true);assert.equal(calls,1);
 assert.equal(await tryExecutionTemplate({messages:[{role:'user',content:'Unfamiliar task'}]},{run:runner,path,code,now}),null);assert.equal(calls,1);
 const trace={messages:[{role:'user',content:query},{role:'assistant',tool_calls:[{id:'c1',type:'function',function:{name:tool,arguments:'{"name":"Hall Lamp"}'}}]},{role:'tool',tool_call_id:'c1',content:JSON.stringify(data)}]};
 assert(candidateFromTurn(trace));assert.equal(await tryExecutionTemplate(trace,{run:runner,path,code,now}),null);
 const learned=await learnExecutionTemplate(trace,{run:async req=>({ok:true,recipe}),path,code,now});assert.equal(learned.text,'Hall Lamp: off.');
 assert.equal(candidateFromTurn({...trace,messages:[...trace.messages,{role:'user',content:'Explain why'}]}),null);
 const other={...recipe,args:{name:'Different Lamp'}};assert(!saveTemplate(query,other,{path,code,now}));assert(!findTemplate(query,{path,code,now}));
 const wq='Turn Hall Lamp on',write={query:wq,kind:'write',tool:'home-assistant_intent__HassTurnOn',args:{name:'Hall Lamp'},expected_entities:['light.hall_lamp'],desired:'on'};saveTemplate(wq,write,{path,code,now});
 const guarded={messages:[{role:'user',content:'Never control this light without checking with me.'},{role:'assistant',content:'Understood'},{role:'user',content:wq}]};assert.equal(await tryExecutionTemplate(guarded,{run:runner,path,code,now}),null);
 const uncertain=await tryExecutionTemplate({messages:[{role:'user',content:wq}]},{run:async()=>({ok:false,write_uncertain:true,message:'Check state before retrying.'}),path,code,now});assert.equal(uncertain.source,'uncertain-write');assert(!findTemplate(wq,{path,code,now}));
 assert.equal(formatProcedure(tool,data),'Hall Lamp: off.');assert(readFileSync(path,'utf8').includes('Conflicting verified interpretations'));
 console.log('PASS: exact matching, zero-LLM execution, unknown fallback, expiry/code invalidation, complete-turn certification, conflicting-interpretation disabling, prior restrictions and uncertain-write no-retry.');
}finally{rmSync(dir,{recursive:true,force:true})}
