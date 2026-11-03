import assert from 'node:assert/strict';import {mkdtempSync,rmSync} from 'node:fs';import {tmpdir} from 'node:os';
const root=mkdtempSync(tmpdir()+'/processing-trace-');process.env.OPENCODE_PROCESSING_DIR=root;
const {beginProcessing,endProcessing,processingEvents}=await import('/home/somdutta/.config/opencode/lib/processing-trace.mjs');
const {renderTimeline}=await import('/home/somdutta/.config/opencode/telegram/timeline.mjs');
try{
 assert.equal(beginProcessing({session:'s',provider:'local',kind:'title',now:1}),null);
 const l=beginProcessing({session:'s',provider:'local',model:'local',now:1000});assert.equal(processingEvents('s',0).at(-1).phase,'local');
 endProcessing(l,{now:5000});const c=beginProcessing({session:'s',provider:'remote',model:'cloud',now:6000});assert.equal(processingEvents('s',0).at(-1).phase,'remote');
 const both=beginProcessing({session:'s',provider:'local',model:'local',now:7000});assert.equal(processingEvents('s',0).at(-1).phase,'both');endProcessing(both,{now:8000});endProcessing(c,{now:9000});assert.equal(processingEvents('s',0).at(-1).phase,'other');
 const text=renderTimeline({startedAt:0,now:8500,events:processingEvents('s',0)});assert(text.includes('Remote model'));assert(text.includes('🟩'));assert(text.includes('🟦'));assert(text.includes('8s elapsed'));assert(!text.includes('%'));
 const fresh=renderTimeline({startedAt:10000,now:12000,events:processingEvents('s',10000)});assert(fresh.includes('Preparing'));assert(!fresh.includes('Remote model'));
 const done=renderTimeline({startedAt:0,now:10000,events:processingEvents('s',0),finished:'⏹ Stopped.'});assert(done.includes('Stopped'));assert(!done.includes('/stop'));
 console.log('PASS primary-request attribution, completion, concurrent routes, stale-turn isolation and elapsed timeline rendering');
}finally{rmSync(root,{recursive:true,force:true})}
