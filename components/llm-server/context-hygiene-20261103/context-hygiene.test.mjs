import test from 'node:test';
import assert from 'node:assert/strict';
import {distillHistory,refreshInstructions,sanitizeContext,validateToolChains,ContextLimitError} from '/home/somdutta/.config/opencode/lib/context-hygiene.mjs';
const now=1800000000000;
const user=content=>({role:'user',content});
const answer=content=>({role:'assistant',content});
const call=(id,args='{}')=>({role:'assistant',content:null,reasoning:'PRIVATE_OLD_REASONING',tool_calls:[{id,type:'function',function:{name:'shell',arguments:args}}]});
const result=(id,content)=>({role:'tool',tool_call_id:id,content});
const tools=[{type:'function',function:{name:'shell',description:'Run a bounded local shell command',parameters:{type:'object',properties:{command:{type:'string'}},required:['command']}}}];
const count=async body=>Math.ceil(JSON.stringify(body).length/4);

test('completed task calls, logs and reasoning never enter follow-up memory',()=>{
 const input={messages:[{role:'system',content:'Keep authorization boundaries.'},user('old task'),call('old','{"command":"RAW_OLD_CALL"}'),result('old','RAW_OLD_LOG'),answer('Target light.alpha is off; confirmation pending.'),user('turn it back on')]};
 const r=distillHistory(input,{now,timeMap:new Map([['old task',now-10000]])});
 const wire=JSON.stringify(r.body);for(const forbidden of ['RAW_OLD_CALL','RAW_OLD_LOG','PRIVATE_OLD_REASONING'])assert.ok(!wire.includes(forbidden));
 assert.ok(wire.includes('light.alpha'));assert.ok(wire.includes('confirmation pending'));validateToolChains(r.body);
});
test('expired or undated history is excluded, even final outcomes',()=>{
 const input={messages:[user('expired'),answer('EXPIRED_OUTCOME'),user('unknown age'),answer('UNDATED_OUTCOME'),user('now')]};
 const r=distillHistory(input,{now,timeMap:new Map([['expired',now-1800001]])});
 assert.deepEqual(r.body.messages,[user('now')]);
});
test('identical repeated prompts do not refresh an old outcome timestamp',()=>{
 const b={messages:[user('same request'),answer('STALE_ANSWER'),user('same request')]};
 const r=distillHistory(b,{now,timeMap:new Map([['same request',[now-1800001,now]]])});
 assert.deepEqual(r.body.messages,[user('same request')]);
});
test('aged unfinished tasks are blocked rather than sending their old raw calls',()=>{
 const b={messages:[user('long task'),call('old'),result('old','old raw evidence')]};
 assert.throws(()=>distillHistory(b,{now,timeMap:new Map([['long task',now-1800001]])}),ContextLimitError);
});
test('expired distilled memory is also removed on subsequent processing',()=>{
 const b={messages:[user('old'),answer('EXPIRES'),user('now')]};
 const a=distillHistory(b,{now,timeMap:new Map([['old',now-1000]])});
 const r=distillHistory(a.body,{now:now+1800001});assert.deepEqual(r.body.messages,[user('now')]);
});
test('an active multi-tool chain and exact write arguments survive cleanup',()=>{
 const input={messages:[user('set targets'),{...call('a','{"entity_id":["light.a","light.b"]}'),tool_calls:[...call('a').tool_calls,...call('b').tool_calls]},result('b','B result'),result('a','A result')]};
 const r=distillHistory(input,{now});assert.deepEqual(r.body,input);validateToolChains(r.body);
});
test('steering retains the initiating request and completed in-flight tool chain',()=>{
 const input={messages:[user('finished old'),answer('done'),user('current task'),call('a'),result('a','fresh evidence'),user('correction: only inspect')]};
 const r=distillHistory(input,{now});assert.deepEqual(r.body.messages,input.messages.slice(2));validateToolChains(r.body);
});
test('orphan, duplicate and pending results are rejected before inference',()=>{
 for(const messages of [[result('missing','x')],[call('a'),result('a','x'),result('a','again')],[call('a')],[call('a'),user('interrupt before result')]])assert.throws(()=>validateToolChains({messages}),ContextLimitError);
});
test('instruction baseline is refreshed and obsolete full-text and diff updates removed',()=>{
 const path='/trusted/policy.md';const suffix="\n\nToday's date: today\n<env>keep environment</env>";
 const b={messages:[{role:'system',content:'BASE\nInstructions from: '+path+'\nOLD RULE'+suffix},user('<system-update>\nThe instructions from '+path+" changed. Here's the diff:\n+obsolete\n</system-update>"),user('<system-update>\nInstructions from: '+path+'\nINTERMEDIATE RULE\n</system-update>'),user('new request')]};
 const r=refreshInstructions(b,{sources:new Map([[path,'CURRENT RULE']])});
 assert.equal(r.messages.length,2);assert.ok(r.messages[0].content.includes('CURRENT RULE'));assert.ok(r.messages[0].content.includes('keep environment'));assert.ok(!JSON.stringify(r).includes('OLD RULE'));
});
test('unknown framework updates are preserved instead of guessed away',()=>{
 const m=user('<system-update>\nNew capability restriction\n</system-update>');
 assert.ok(refreshInstructions({messages:[m,user('now')]},{sources:new Map()}).messages.some(x=>x.content===m.content));
});
test('large active JSON is archived as explicitly incomplete recoverable evidence',async()=>{
 const input={tools,messages:[user('aggregate the records'),call('a'),result('a',JSON.stringify(Array.from({length:3000},(_,i)=>({id:i,value:i%7}))))]};
 const r=await sanitizeContext(input,{now,count});const evidence=r.body.messages.at(-1).content;
 assert.ok(evidence.includes('BOUNDED UNTRUSTED TOOL EVIDENCE'));assert.ok(evidence.includes('incomplete'));assert.ok(evidence.includes('dataSnapshot'));assert.ok(evidence.length<4100);validateToolChains(r.body);
});
test('oversized user requests are rejected, never silently truncated',async()=>{
 const prompt='x'.repeat(280000);await assert.rejects(sanitizeContext({messages:[user(prompt)]},{count}),ContextLimitError);assert.equal(prompt.length,280000);
});
test('documentation compaction preserves full schema constraints and enums',async()=>{
 const input={tools:[{type:'function',function:{name:'safe_write',description:'x'.repeat(3000),parameters:{type:'object',properties:{mode:{type:'string',enum:['no-write','verified-write'],description:'y'.repeat(3000)}},required:['mode'],additionalProperties:false}}}],messages:[user('inspect')]};
 const r=await sanitizeContext(input,{count:async b=>b.tools[0].function.description.length>700?9000:3000});
 assert.deepEqual(r.body.tools[0].function.parameters.required,['mode']);assert.deepEqual(r.body.tools[0].function.parameters.properties.mode.enum,['no-write','verified-write']);assert.equal(r.body.tools[0].function.parameters.additionalProperties,false);
});
test('multimodal current input is retained unchanged',()=>{
 const m={role:'user',content:[{type:'text',text:'Analyze this clip'},{type:'video_url',video_url:{url:'data:video/mp4;base64,AAAA'}}]};assert.deepEqual(distillHistory({messages:[m]},{now}).body.messages,[m]);
});
test('cleanup is idempotent and cannot treat previous memory as a new task',async()=>{
 const input={messages:[user('old'),answer('verified result'),user('now')]};const options={now,timeMap:new Map([['old',now-1000]]),count};
 const a=await sanitizeContext(input,options),b=await sanitizeContext(a.body,options);assert.deepEqual(b.body,a.body);
});
test('16K triggers optional-memory compaction while retaining latest follow-up referent',async()=>{
 const input={messages:[user('first'),answer('earlier outcome'),user('second'),answer('Most recent target is light.beta'),user('continue current task'),call('a','{"exact":"keep"}'),result('a','current evidence')]};
 const count=async b=>JSON.stringify(b).includes('earlier outcome')?16500:15000;
 const r=await sanitizeContext(input,{now,timeMap:new Map([['first',now-2000],['second',now-1000]]),count});
 assert.equal(r.stats.inputTokens,15000);assert.equal(r.stats.memoryReduced,true);assert.ok(JSON.stringify(r.body).includes('light.beta'));assert.ok(!JSON.stringify(r.body).includes('earlier outcome'));
 assert.equal(r.body.messages.find(m=>m.tool_calls)?.tool_calls[0].function.arguments,'{"exact":"keep"}');validateToolChains(r.body);
});
test('legitimate active evidence can exceed the cleanup trigger without a 413',async()=>{
 const input={messages:[user('current task'),call('a'),result('a','scoped evidence')]};
 const r=await sanitizeContext(input,{count:async()=>17000});assert.equal(r.stats.aboveCompactionTarget,true);validateToolChains(r.body);
});
