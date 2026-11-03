import assert from 'node:assert/strict';import {mkdtempSync,writeFileSync,readFileSync,rmSync,existsSync} from 'node:fs';import {tmpdir,homedir} from 'node:os';import {join} from 'node:path';
const dir=mkdtempSync(join(tmpdir(),'bridge-quota-test-'));const quota=join(dir,'quota.json'),log=join(dir,'calls.jsonl'),fake=join(dir,'opencode');
process.env.OPENCODE_FREE_QUOTA_FILE=quota;process.env.OPENCODE_TG_MODEL='opencode/glm-5.3-flash-free';process.env.OPENCODE_TG_BIN=fake;
writeFileSync(fake,`#!/home/somdutta/.nvm/versions/node/v24.22.1/bin/node
import {appendFileSync} from 'node:fs';
const args=process.argv.slice(2),model=args[args.indexOf('-m')+1];appendFileSync(${JSON.stringify(log)},JSON.stringify({model})+'\\n');
if(model.startsWith('opencode/')){
 if(args.some(a=>a==='partial'))console.log(JSON.stringify({type:'tool_use',part:{type:'tool',messageID:'msg_fixture',tool:'fixture',state:{status:'completed'}}}));
 console.log(JSON.stringify({type:'error',error:{type:'provider.free-limit',message:'Free usage limit reached',retryAfterMs:300000}}));
}else console.log(JSON.stringify({type:'text',part:{type:'text',messageID:'msg_fixture',text:'paid fallback okay'}}));
`,{mode:0o700});
try{
 const {runOpenCode}=await import(homedir()+'/.config/opencode/telegram/bridge.mjs');
 let r=await runOpenCode('ses_fixture_quota','fresh',{timeout:5000});assert(r.ok&&r.text==='paid fallback okay');
 let calls=readFileSync(log,'utf8').trim().split('\n').map(JSON.parse);assert.deepEqual(calls.map(c=>c.model),['opencode/glm-5.3-flash-free','openrouter/deepseek/deepseek-v4.1-flash-1017']);
 rmSync(quota);writeFileSync(log,'');
 r=await runOpenCode('ses_fixture_partial','partial',{timeout:5000});assert(!r.ok&&r.text.includes('not replayed'));calls=readFileSync(log,'utf8').trim().split('\n').map(JSON.parse);assert.equal(calls.length,1);
 writeFileSync(log,'');r=await runOpenCode('ses_fixture_cooldown','fresh',{timeout:5000});assert(r.ok);calls=readFileSync(log,'utf8').trim().split('\n').map(JSON.parse);assert.equal(calls.length,1);assert(calls[0].model.startsWith('openrouter/'));
 console.log('PASS: real bridge terminal-quota retry once, no retry after tool activity, and cooldown skips exhausted provider; no live model or Telegram calls.');
}finally{rmSync(dir,{recursive:true,force:true})}
