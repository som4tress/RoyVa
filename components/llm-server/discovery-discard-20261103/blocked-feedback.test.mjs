import test from 'node:test';import assert from 'node:assert/strict';import {mkdtempSync,rmSync} from 'node:fs';import {tmpdir} from 'node:os';
const dir=mkdtempSync(tmpdir()+'/discard-votes-');process.env.AGENT_DISCARD_HOME=dir+'/markers';
const {markDiscarded}=await import('/home/somdutta/Projects/agent-learning/src/discard.mjs');
const {recordFeedback,status}=await import('/home/somdutta/Projects/agent-learning/src/feedback.mjs');
test('a late positive vote cannot revive a discarded session or authorize creation',()=>{
 const target={sessionID:'ses_discarded_feedback_unit',messageID:'msg_example',digest:'a'.repeat(64)};
 try{markDiscarded(target.sessionID);assert.equal(status(target,{path:dir+'/ledger'}).buildAllowed,false);assert.throws(()=>recordFeedback({target,action:'accept',actor:'user',source:'test'},{path:dir+'/ledger'}),/discarded/);assert.equal(recordFeedback({target,action:'reject',actor:'user',source:'test'},{path:dir+'/ledger'}).discarded,true);}finally{rmSync(dir,{recursive:true,force:true});}
});
