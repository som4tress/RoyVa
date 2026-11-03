import assert from 'node:assert/strict';
import {hostname} from 'node:os';
import {mkdtempSync,rmSync} from 'node:fs';import {tmpdir} from 'node:os';import {join} from 'node:path';
import adapter from '/home/somdutta/.config/opencode/lib/execution-adapters/local-host-info.mjs';
import {candidateFromTurn,learnExecutionTemplate,tryExecutionTemplate,saveTemplate} from '/home/somdutta/.config/opencode/lib/execution-templates.mjs';
const dir=mkdtempSync(join(tmpdir(),'generic-adapter-test-')),path=join(dir,'templates.json'),code='host-test',query='What is the local kernel version?';
try{
 const body={messages:[{role:'user',content:query},{role:'assistant',tool_calls:[{id:'x',function:{name:'shell',arguments:'{"command":"uname -r"}'}}]},{role:'tool',tool_call_id:'x',content:'7.3.0-example\n'}]};
 assert(candidateFromTurn(body));const learned=await learnExecutionTemplate(body,{path,code});assert(learned.text.startsWith('Kernel: '));
 const replay=await tryExecutionTemplate({messages:[{role:'user',content:query}]},{path,code});assert(replay.zeroLLM&&replay.text.startsWith('Kernel: '));
 for(const command of ['uname -r; touch /tmp/unsafe','rm -rf /','sudo uname -r','ssh elsewhere uname -r']){
  const r=await adapter.run({operation:'certify',tool:'shell',args:{command},query,data:{stdout:'ignored'}});assert(!r.ok);
 }
 assert(!(await adapter.run({operation:'certify',tool:'shell',args:{command:'uname -r'},query:'Install software then show kernel version',data:{stdout:'ignored'}})).ok);
 assert(!(await adapter.run({operation:'execute',query,recipe:{args:{command:'uname -r'},expectedHost:'different-host'}})).ok);
 assert.equal(saveTemplate(query,{kind:'write',tool:'shell',adapter:'local-host-info',args:{command:'uname -r'}},{path,code}),false);
 console.log('PASS: generic adapter learns and replays fresh read-only host data; arbitrary shell, remote host, compound actions and undeclared writes rejected.');
}finally{rmSync(dir,{recursive:true,force:true})}
