import assert from 'node:assert/strict';import generic,{LOCAL_BUDGET_MS} from '/home/somdutta/.config/opencode/plugins/procedure-memory/index.js';import ha,{HA_LOCAL_MS,HA_TOTAL_MS} from '/home/somdutta/.config/opencode/plugins/ha-mcp-routing/index.js';
let clock=Date.now();const original=Date.now;Date.now=()=>clock;
try{
 const hooks={},tool={},models=[];let current={providerID:'openrouter',id:'deepseek/deepseek-v4.1-flash-1017'};
 await generic.setup({session:{hook:async(n,f)=>hooks[n]=f,get:async()=>({model:current,location:{directory:'/tmp/policy-unit'}}),switchModel:async({model})=>{current=model;models.push(model)}},tool:{hook:async(n,f)=>tool[n]=f}});
 await hooks.prompt({sessionID:'policy-unit-generic',prompt:{text:'Explain a general topic. '+ 'x'.repeat(1250)}});assert.equal(current.providerID,'evo-agent');
 clock+=31000;await assert.rejects(tool['execute.before']({sessionID:'policy-unit-generic',tool:'shell',input:{command:'read-only probe'}}));assert.equal(current.providerID,'openrouter');assert.equal(LOCAL_BUDGET_MS,30000);
 const cloudRequest={sessionID:'policy-unit-generic',model:current,headers:{'x-media-timeout-ms':'1'},kind:'primary'};await hooks['model.request'](cloudRequest);assert.equal(cloudRequest.headers['x-media-timeout-ms'],'120000');
 const h={},storage=new Map();current={providerID:'evo-agent',id:'qwen36-agent'};
 await ha.setup({options:{phraseStore:'/tmp/policy-none-phrases.json',learningStore:'/tmp/policy-none-routes.json'},storage:{get:async k=>storage.get(k),set:async(k,v)=>storage.set(k,v),remove:async k=>storage.delete(k)},session:{hook:async(n,f)=>h[n]=f,get:async()=>({model:current}),switchModel:async({model})=>current=model},permission:{hook:async()=>{}}});
 await h.prompt({sessionID:'policy-unit-ha',prompt:{text:'Is Den Switch on?'}});clock+=HA_LOCAL_MS+1;
 await h.context({sessionID:'policy-unit-ha',tools:{'ha-history_get_device_status':{}},system:[]});assert.equal(current.providerID,'openrouter');
 const req={sessionID:'policy-unit-ha',model:current,headers:{},kind:'primary'};await h['model.request'](req);assert.equal(Number(req.headers['x-media-timeout-ms']),120000);
 clock+=4000;const stillFresh={sessionID:'policy-unit-ha',model:current};await h.retry(stillFresh);assert.notEqual(stillFresh.decision?.retry,false);clock+=120000;const retry={sessionID:'policy-unit-ha',model:current};await h.retry(retry);assert.equal(retry.decision.retry,false);
 console.log('PASS: local first, 30s including pre-tool time; HA local deadline hands over with fresh 120s cloud budget; cloud is stopped only when its own budget expires.');
}finally{Date.now=original}
