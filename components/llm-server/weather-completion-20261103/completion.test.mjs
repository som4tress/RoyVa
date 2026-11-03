import test from 'node:test';import assert from 'node:assert/strict';
import {completionProblem,discoveryContinuation,wireSummary,currentRequest} from '/home/somdutta/.config/opencode/lib/completion-check.mjs';
const prompt='What does the weather look like till 21 Nov?';const body={messages:[{role:'user',content:prompt}],tools:[{type:'function',function:{name:'discover_capabilities'}}]};
test('an echo is not completion; literal-copy tasks remain valid',()=>{assert.equal(completionProblem(body,'"'+prompt+'"'),'prompt_echo');assert.equal(completionProblem({messages:[{role:'user',content:'Repeat exactly this question: '+prompt}]},prompt),null);assert.equal(completionProblem({messages:[{role:'user',content:'Hello'}]},'Hello'),null);});
test('unsupported tool refusal needs discovery; evidence and coverage limits remain valid',()=>{assert.equal(completionProblem(body,"I don't have forecast tools."),'unchecked_capability_refusal');assert.equal(completionProblem(body,'The source only covers the next 16 days; later dates are unavailable.'),null);assert.equal(completionProblem({...body,messages:[...body.messages,{role:'assistant',tool_calls:[{function:{name:'discover_capabilities'}}]}]},"I don't have access to that tool."),null);});
test('recovery preserves receipts, usage and provider reasoning without repeating actions',()=>{
 const response={id:'x',model:'qwen',choices:[{index:0,message:{role:'assistant',content:prompt,reasoning:'retain provider field'},finish_reason:'stop'}],usage:{prompt_tokens:120,completion_tokens:13}};
 const repaired=discoveryContinuation(JSON.stringify(response),'qwen'),j=JSON.parse(repaired),s=wireSummary(repaired);assert.equal(s.finished,false);assert.equal(s.toolCalls,true);assert.equal(s.answer,'');assert.equal(j.choices[0].message.reasoning,'retain provider field');assert.equal(j.choices[0].message.tool_calls[0].function.name,'discover_capabilities');assert.deepEqual(j.usage,response.usage);
 const sse='data: '+JSON.stringify({id:'x',choices:[{index:0,delta:{content:prompt},finish_reason:'stop'}]})+'\n\ndata: '+JSON.stringify({choices:[],usage:response.usage})+'\n\ndata: [DONE]\n\n';const out=wireSummary(discoveryContinuation(sse,'qwen'));assert.equal(out.toolCalls,true);assert.equal(out.finished,false);assert.equal(out.answer,'');assert.deepEqual(out.usage,response.usage);
});
test('text arrays and existing tool results retain the current user goal',()=>{assert.equal(currentRequest({messages:[{role:'user',content:[{type:'text',text:prompt}]},{role:'assistant',tool_calls:[{id:'old-write',function:{name:'authorized_action'}}]},{role:'tool',tool_call_id:'old-write',content:'Already executed'}]}),prompt);});
test('source attribution needs task evidence across domains, not a previous answer or a catalog',()=>{
 const output='Current quote is 123.45.\nSource: market data API';
 assert.equal(completionProblem(body,output),'source_claim_without_evidence');
 assert.equal(completionProblem({...body,messages:[{role:'assistant',content:'Old result'},{role:'tool',tool_call_id:'old',content:'Old source'},...body.messages]},output),'source_claim_without_evidence');
 const called=[...body.messages,{role:'assistant',tool_calls:[{id:'c',function:{name:'discover_capabilities'}}]},{role:'tool',tool_call_id:'c',content:'Catalog only'}];
 assert.equal(completionProblem({...body,messages:called},output),'source_claim_without_evidence');
 const actual=[...body.messages,{role:'assistant',tool_calls:[{id:'r',function:{name:'webfetch'}}]},{role:'tool',tool_call_id:'r',content:'Current quote: 123.45'}];
 assert.equal(completionProblem({...body,messages:actual},output),null);
 assert.equal(completionProblem(body,'Which exchange and currency should I use?'),null);
});
