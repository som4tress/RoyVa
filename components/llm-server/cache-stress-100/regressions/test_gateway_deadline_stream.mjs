import assert from 'node:assert/strict';import http from 'node:http';import {spawn} from 'node:child_process';import {homedir} from 'node:os';
const backend=http.createServer(async(req,res)=>{let text='';for await(const c of req)text+=c;const fast=text.includes('fast-fixture');res.writeHead(200,{'content-type':'text/event-stream'});res.write('data: '+JSON.stringify({id:'fixture',object:'chat.completion.chunk',choices:[{index:0,delta:{content:'partial'},finish_reason:null}]})+'\n\n');setTimeout(()=>{res.end('data: '+JSON.stringify({id:'fixture',object:'chat.completion.chunk',choices:[{index:0,delta:{content:' complete'},finish_reason:'stop'}]})+'\n\ndata: [DONE]\n\n')},fast?20:600)});
await new Promise(r=>backend.listen(18012,'127.0.0.1',r));
const child=spawn(process.execPath,[homedir()+'/.config/opencode/lib/media-deadline-proxy.mjs'],{env:{...process.env,MEDIA_PROXY_PORT:'18011',VLLM_API_KEY:'fixture-only',OPENCODE_TEST_AGENT_ENDPOINT:'http://127.0.0.1:18012/v1/chat/completions'},stdio:['ignore','ignore','pipe']});
try{
 for(let i=0;i<100;i++){try{if((await fetch('http://127.0.0.1:18011/health')).ok)break}catch{}await new Promise(r=>setTimeout(r,30));}
 const call=async(text,budget)=>{const r=await fetch('http://127.0.0.1:18011/generic-agent/v1/chat/completions',{method:'POST',headers:{'content-type':'application/json','x-media-timeout-ms':String(budget)},body:JSON.stringify({model:'fixture',stream:true,messages:[{role:'user',content:text}]})});return {status:r.status,body:await r.text()};};
 const slow=await call('slow-fixture',100);assert.equal(slow.status,504);assert.ok(!slow.body.includes('partial'));
 const fast=await call('fast-fixture',2000);assert.equal(fast.status,200);assert.ok(fast.body.includes('finish_reason')&&fast.body.includes('[DONE]'));
 console.log('PASS: interrupted local stream yields clean HTTP 504 with no leaked partial answer; completed stream remains valid. No real model or HA calls.');
}finally{child.kill('SIGTERM');backend.close();}
