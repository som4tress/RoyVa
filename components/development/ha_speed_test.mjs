import assert from 'node:assert/strict';
import plugin from '/home/somdutta/.config/opencode/plugins/ha-mcp-routing/index.js';
const hooks={};let model={providerID:'openrouter',id:'cloud'};
await plugin.setup({tool:{hook:async(n,f)=>hooks[n]=f},session:{hook:async(n,f)=>hooks[n]=f,get:async()=>({model}),switchModel:async x=>model=x.model},permission:{hook:async(n,f)=>hooks['permission']=f}});
const read='home-assistant_homeassistant__GetLiveContext',write='home-assistant_intent__HassTurnOn';
async function context(id,text){await hooks.prompt({sessionID:id,prompt:{text}});const e={sessionID:id,model,system:[],options:{},tools:{[read]:{},[write]:{},shell:{}}};await hooks.context(e);return e;}
const c=await context('status-speed-test','What is Shivangsh room light status');assert.deepEqual(Object.keys(c.tools),[read]);
const original={messages:[{role:'system',content:'Large original instructions'},{role:'user',content:'What is Shivangsh room light status'}],tools:[{type:'function',function:{name:read}}],chat_template_kwargs:{enable_thinking:true}};
let req={sessionID:'status-speed-test',kind:'primary',model,request:new Request('http://localhost/test',{method:'POST',body:JSON.stringify(original)})};await hooks['http.request'](req);let b=await req.request.json();assert.equal(b.chat_template_kwargs.enable_thinking,false);assert.equal(b.max_tokens,384);assert(!JSON.stringify(b.messages).includes('Large original instructions'));assert.equal(b.messages[1].content,original.messages[1].content);assert.equal(b.tool_choice,'required');
await hooks['execute.after']({sessionID:'status-speed-test',tool:read,status:'completed',input:{name:'Shivi',domain:['light']},result:{output:'test state'}});
req={sessionID:'status-speed-test',kind:'primary',model,request:new Request('http://localhost/test',{method:'POST',body:JSON.stringify(original)})};await hooks['http.request'](req);b=await req.request.json();assert.equal(b.chat_template_kwargs.enable_thinking,false);assert(!b.tool_choice);
const action=await context('action-speed-test','Turn on the kitchen light');assert(Object.keys(action.tools).includes(write));
const ordinary=await context('ordinary-speed-test','Explain how JavaScript promises work');assert(Object.keys(ordinary.tools).includes('shell'));
console.log('PASS: status is read-only and compact, thinking off for both steps, current question retained; action and general routes preserved.');

