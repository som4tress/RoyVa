import test from 'node:test';import assert from 'node:assert/strict';
import router from '/home/somdutta/.config/opencode/plugins/ha-mcp-routing/index.js';
import {localContinuationEstimate as predict} from '/home/somdutta/.config/opencode/lib/local-progress-budget.mjs';
const now=1800000000000;
test('one deadline and the ten-second overrun threshold',()=>{
 assert.equal(predict({startedAt:now-59000,now,lastModelMs:5000,budgetMs:60000}).escalate,false);
 assert.equal(predict({startedAt:now-59000,now,lastModelMs:12000,budgetMs:60000}).escalate,true);
 assert.equal(predict({startedAt:now-60000,now,lastModelMs:1,budgetMs:60000}).escalate,true);
});
async function harness(){const hooks={session:{},tool:{},permission:{}};const data=new Map();const record=kind=>({hook:async(name,fn)=>{(hooks[kind][name]??=[]).push(fn)}});const ctx={session:{...record('session'),get:async()=>({metadata:{},model:{providerID:'evo-agent',id:'qwen36-agent'}}),switchModel:async()=>{throw new Error('Unexpected routing override')}},storage:{get:async k=>data.get(k),set:async(k,v)=>data.set(k,v),remove:async k=>data.delete(k)},tool:record('tool'),permission:record('permission')};await router.setup(ctx);return hooks}
test('entity prompt does not prune tools, change model or impose output caps',async()=>{
 const h=await harness();for(const fn of h.session.prompt)await fn({sessionID:'audit-entities',prompt:{text:'show me all the entities that are on in my house today'}});
 const tools={websearch:{},'ha-history_get_device_status':{},'ha-history_get_on_entities_with_context':{},'home-assistant_intent__HassTurnOff':{}};
 const event={sessionID:'audit-entities',tools:structuredClone(tools),system:[],options:{maxTokens:8192},model:{providerID:'evo-agent'}};
 for(const fn of h.session.context)await fn(event);assert.deepEqual(event.tools,tools);assert.equal(event.options.maxTokens,8192);assert.deepEqual(event.system,[]);
 await assert.rejects(h.tool['execute.before'][0]({sessionID:'audit-entities',tool:'home-assistant_intent__HassTurnOff',input:{name:'any'}}),/read-only/);
});
test('write safeguard still blocks an unverified pronoun target',async()=>{
 const h=await harness();for(const fn of h.session.prompt)await fn({sessionID:'audit-followup',prompt:{text:'turn it off'}});
 await assert.rejects(h.tool['execute.before'][0]({sessionID:'audit-followup',tool:'home-assistant_intent__HassTurnOff',input:{name:'guessed'}}),/no uniquely verified target/);
});
