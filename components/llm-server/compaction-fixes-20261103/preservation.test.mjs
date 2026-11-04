import test from 'node:test';import assert from 'node:assert/strict';
import {readFileSync,mkdtempSync,writeFileSync,rmSync} from 'node:fs';import {tmpdir} from 'node:os';import {createHash} from 'node:crypto';
import {sanitizeContext,distillHistory,ContextLimitError} from '/home/somdutta/.config/opencode/lib/context-hygiene.mjs';
import {cleanToolEvidence} from '/home/somdutta/.config/opencode/lib/evidence-window.mjs';
import {compactSource,compactWebMessages} from '/home/somdutta/.config/opencode/lib/read-context.mjs';
import {optimizeCloudRequest} from '/home/somdutta/.config/opencode/lib/cloud-context-optimizer.mjs';
const user=content=>({role:'user',content}),answer=content=>({role:'assistant',content});
const tool={type:'function',function:{name:'shell',parameters:{type:'object',properties:{}}}};
const body=(content,name='websearch')=>({tools:[tool],messages:[user('Read all dated records'),{role:'assistant',tool_calls:[{id:'a',type:'function',function:{name,arguments:'{"url":"https://example.test/feed"}'}}]},{role:'tool',tool_call_id:'a',content}]});
const count=async()=>17000,now=1800000000000;
const settings={enabled:true,semanticEnabled:false,evidenceWindows:true};
test('archived weather evidence survives every active cleanup path exactly',async()=>{
 const raw=readFileSync('/home/somdutta/.local/share/opencode/cloud-context/evidence-v1/92bd784effad3aa8009ad316c307e3806137cd954033cf67aae182402556afa8.txt','utf8');
 const input=body(raw),before=structuredClone(input);const r=await sanitizeContext(input,{count});
 const cloud=await optimizeCloudRequest(r.body,{settings});assert.equal(cloud.messages.at(-1).content,raw);assert.deepEqual(input,before);assert.equal(r.stats.archivedResults,0);
});
test('web pages and feeds retain full text and all entries',()=>{
 const feed='<rss>'+Array.from({length:20},(_,i)=>`<item><title>${i}</title><description>${'details '.repeat(120)}</description></item>`).join('')+'</rss>';
 assert.equal(compactSource(feed,'all articles','url'),feed);assert.deepEqual(compactWebMessages(body(feed,'webfetch').messages,'latest'),body(feed,'webfetch').messages);
 const page='x'.repeat(20000)+'CRITICAL END';assert.equal(compactSource(page,'summary','url'),page);
});
test('cloud never reuses old lossy projection cache entries',async()=>{
 const dir=mkdtempSync(tmpdir()+'/royva-projection-');try{
 const raw='<rss>'+ '<item>dated evidence</item>'.repeat(1000)+'</rss>',input=body(raw,'webfetch');
 const task=JSON.stringify(input.messages[0].content),key=createHash('sha256').update('projection-v3\n'+task+'\n'+raw).digest('hex');
 writeFileSync(dir+'/'+key+'.json',JSON.stringify({text:'STALE LOSSY PROJECTION'}));
 const r=await optimizeCloudRequest(input,{settings:{...settings,cacheDir:dir}});assert.equal(r.messages.at(-1).content,raw);
 }finally{rmSync(dir,{recursive:true,force:true})}
});
test('duplicate evidence is still deduplicated; first result and arguments stay exact',()=>{
 const input=body('record\n'.repeat(500));input.messages[1].tool_calls.push({id:'b',...input.messages[1].tool_calls[0],id:'b'});input.messages.push({role:'tool',tool_call_id:'b',content:input.messages[2].content});
 const r=cleanToolEvidence(input);assert.equal(r.duplicates,1);assert.equal(r.body.messages[2].content,input.messages[2].content);assert.match(r.body.messages[3].content,/byte-identical/);assert.deepEqual(r.body.messages[1],input.messages[1]);
});
test('all schema descriptions, including enum/default literals, remain exact above 16K',async()=>{
 const tools=[{type:'function',function:{name:'test',description:'doc'.repeat(1000),parameters:{type:'object',properties:{value:{enum:[{description:'literal'.repeat(1000)}],default:{description:'default'.repeat(1000)}}}}}}];
 const r=await sanitizeContext({tools,messages:[user('inspect')]},{count});assert.deepEqual(r.body.tools,tools);
});
test('complete long requests and failed-action qualifiers survive history memory',()=>{
 const request='Inspect '.repeat(700)+' DO NOT CHANGE ANY DEVICES',outcome='Result '.repeat(400)+' ACTION FAILED; no state change confirmed.';
 const r=distillHistory({messages:[user(request),answer(outcome),user('continue')]},{now,timeMap:new Map([[request,now-1000]])});
 const memory=r.body.messages.find(m=>m.content.startsWith('[RECENT CONVERSATION MEMORY:'));const entries=JSON.parse(memory.content.slice(memory.content.indexOf('\n')+1));assert.equal(entries[0].request,request);assert.equal(entries[0].outcome,outcome);
});
test('crossing 16K no longer discards older selected exchange',async()=>{
 const r=await sanitizeContext({messages:[user('first'),answer('first constraint'),user('second'),answer('second result'),user('continue')]},{now,timeMap:new Map([['first',now-2000],['second',now-1000]]),count});
 assert.match(JSON.stringify(r.body),/first constraint/);assert.match(JSON.stringify(r.body),/second result/);assert.equal(r.stats.memoryReduced,false);
});
test('real input guard and tool-chain validation still reject invalid requests',async()=>{
 await assert.rejects(sanitizeContext(body('full evidence'),{count:async()=>65537}),ContextLimitError);
 await assert.rejects(sanitizeContext({messages:[{role:'tool',tool_call_id:'missing',content:'x'}]},{count}),/Orphan/);
});
