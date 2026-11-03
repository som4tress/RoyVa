import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';import vm from 'node:vm';import {pollBackoffMs} from '/home/somdutta/.config/opencode/lib/telegram-poll-backoff.mjs';
assert.equal(pollBackoffMs(1),3000);assert.equal(pollBackoffMs(2),6000);assert.equal(pollBackoffMs(20),60000);assert.equal(pollBackoffMs(1,120000),120000);
const source=readFileSync('/home/somdutta/.config/opencode/telegram/bridge.mjs','utf8');const pollSource=source.slice(source.indexOf('async function poll()'),source.indexOf('// Exported so',source.indexOf('async function poll()'))).trim();
const poll=vm.runInNewContext('('+pollSource+')',{state:{},tg:async()=>({ok:false,parameters:{retry_after:7}})});await assert.rejects(poll(),e=>e.retryAfterMs===7000);
const plugin=(await import('/home/somdutta/.config/opencode/plugins/procedure-memory/index.js')).default;
const realNow=Date.now,realSet=globalThis.setTimeout,realClear=globalThis.clearTimeout;let now=realNow();globalThis.setTimeout=()=>({unref(){}});globalThis.clearTimeout=()=>{};Date.now=()=>now;
try{
 const hooks={},tools={},session={model:{providerID:'evo-agent',id:'qwen36-agent'},location:{directory:'/tmp/handoff-regression'},time:{busy:now,idle:0}};
 await plugin.setup({session:{hook:async(n,f)=>hooks[n]=f,get:async()=>session,switchModel:async({model})=>session.model=model,context:async()=>[]},tool:{hook:async(n,f)=>tools[n]=f}});
 const sid='unit-stale-handoff-20261103';await hooks.prompt({sessionID:sid,prompt:{text:'Investigate /tmp/fixture safely. '+'x'.repeat(1300)}});
 await hooks['model.request']({sessionID:sid,model:{providerID:'evo-agent',id:'qwen36-agent'},headers:{},kind:'primary'});now+=14000;
 await tools['execute.before']({sessionID:sid});await hooks.context({sessionID:sid,tools:{shell:{}},system:[]});assert.equal(session.model.providerID,'openrouter');
 const stale={sessionID:sid,model:{providerID:'evo-agent',id:'qwen36-agent'},headers:{},kind:'primary'};await hooks['model.request'](stale);assert.equal(stale.headers['x-media-budget-exhausted'],'true');assert.equal(stale.headers['x-media-timeout-ms'],'1');
 const retry={sessionID:sid,model:{providerID:'evo-agent',id:'qwen36-agent'}};await hooks.retry(retry);assert.equal(retry.decision.retry,true);
 const cloud={sessionID:sid,model:session.model,headers:{...stale.headers},kind:'primary'};await hooks['model.request'](cloud);assert(!cloud.headers['x-media-budget-exhausted']);assert.equal(cloud.baseURL,'http://127.0.0.1:8011/generic-cloud/v1');
 console.log('PASS: failed poll throws/backoff/retry-after; early handoff blocks already-built local request; cloud retry clears stale rejection; tools remain available.');
}finally{Date.now=realNow;globalThis.setTimeout=realSet;globalThis.clearTimeout=realClear}
