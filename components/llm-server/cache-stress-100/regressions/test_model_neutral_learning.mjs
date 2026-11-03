import assert from 'node:assert/strict';import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';import {tmpdir} from 'node:os';import {join} from 'node:path';
import {cloudModel,cloudModelID} from '/home/somdutta/.config/opencode/lib/routing-policy.mjs';
import {learnCompletedTask,recallTask} from '/home/somdutta/.config/opencode/lib/task-learning.mjs';
import {fingerprint,saveTemplate,findTemplate} from '/home/somdutta/.config/opencode/lib/execution-templates.mjs';
const dir=mkdtempSync(join(tmpdir(),'model-neutral-'));const policy=join(dir,'policy.json'),tasks=join(dir,'tasks.json'),templates=join(dir,'templates.json');process.env.OPENCODE_ROUTING_POLICY_FILE=policy;
try{
 writeFileSync(policy,JSON.stringify({cloud:{providerID:'openrouter',id:'vendor/model-one'}}));assert.equal(cloudModel().id,'vendor/model-one');
 learnCompletedTask({task:'Read a host kernel version',workspace:dir,sessionID:'model-one',source:'Synthetic model-neutral test'},tasks);
 const code=fingerprint();saveTemplate('Read a host kernel version',{tool:'ha-history_get_device_status',kind:'read',args:{name:'Synthetic target'},expected_entities:['light.synthetic']},{path:templates,code});
 writeFileSync(policy,JSON.stringify({cloud:{providerID:'openrouter',id:'vendor/model-two'}}));assert.equal(cloudModelID(),'openrouter/vendor/model-two');
 assert.equal((await recallTask('Read a host kernel version',dir,{path:tasks})).match,'exact');assert.equal(fingerprint(),code);assert.ok(findTemplate('Read a host kernel version',{path:templates,code}));
 console.log('PASS: changing OpenRouter model dynamically preserves learned task recall and validated templates; no production setting or real model was changed.');
}finally{delete process.env.OPENCODE_ROUTING_POLICY_FILE;rmSync(dir,{recursive:true,force:true})}
