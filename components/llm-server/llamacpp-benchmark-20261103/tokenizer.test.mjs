import assert from 'node:assert/strict';
import {countInput} from '/home/somdutta/.config/opencode/lib/context-hygiene.mjs';
const original=globalThis.fetch;
const body={model:'qwen36-agent',messages:[{role:'user',content:'hello'}],tools:[{type:'function',function:{name:'test',parameters:{type:'object',properties:{}}}}]};
try {
 let calls=[];
 globalThis.fetch=async(url,options)=>{calls.push(url);return Response.json({count:17})};
 assert.equal(await countInput(body),17);assert.equal(calls.length,1);
 calls=[];globalThis.fetch=async(url,options)=>{const payload=JSON.parse(options.body);calls.push(url);
  if(url.endsWith('/apply-template')){assert.deepEqual(payload.tools,body.tools);assert.deepEqual(payload.messages,body.messages);return Response.json({prompt:'<rendered-with-tool-schema>'})}
  if(payload.content){assert.equal(payload.content,'<rendered-with-tool-schema>');assert.equal(payload.parse_special,true);return Response.json({tokens:[1,2,3,4]})}
  return Response.json({tokens:[]});};
 assert.equal(await countInput(body),4);assert.equal(calls.length,3);
 globalThis.fetch=async(url)=>Response.json(url.endsWith('/apply-template')?{prompt:null}:{tokens:[]});
 await assert.rejects(countInput(body),/Invalid rendered input/);
 globalThis.fetch=async()=>Response.json({bad:true});await assert.rejects(countInput(body),/Invalid input token count/);
 console.log('4 tokenizer compatibility checks passed');
}finally{globalThis.fetch=original}
