import assert from 'node:assert/strict';import {readFileSync,mkdtempSync,rmSync} from 'node:fs';import {tmpdir} from 'node:os';
import {renderTimeline,describeTool} from '/home/somdutta/.config/opencode/telegram/timeline.mjs';
import {LOCAL_BUDGET_MS} from '/home/somdutta/.config/opencode/plugins/procedure-memory/index.js';
import {HA_LOCAL_MS,HA_TOTAL_MS,HA_CLOUD_MS} from '/home/somdutta/.config/opencode/plugins/ha-mcp-routing/index.js';
assert.equal(LOCAL_BUDGET_MS,60000);assert.equal(HA_LOCAL_MS,42000);assert.equal(HA_TOTAL_MS,45000);assert.equal(HA_CLOUD_MS,120000);
const events=[{at:1000,phase:'local',models:['example-local']},{at:9000,phase:'other',models:[]},{at:10000,phase:'remote',models:['vendor/example-remote']}];
let s=renderTimeline({startedAt:0,now:12000,events,models:['vendor/example-remote']});assert(s.includes('Remote'));assert(s.includes('example-remote'));assert(s.includes('generating next action'));assert(s.includes('▰'));assert(s.includes('▱'));assert(!s.includes('🟩'));assert(!s.includes('%'));
s=renderTimeline({startedAt:0,now:9500,events,activity:{at:9200,tool:'ha-history_get_device_status',status:'running'}});assert(s.includes('Reading live device status'));assert(!s.includes('generating next action'));assert(s.includes('OpenCode'));
s=renderTimeline({startedAt:0,now:15000,events:[...events,{at:14000,phase:'other',models:[]}],finished:'✓ Finished.'});assert(s.includes('Last model: example-remote'));assert(!s.includes('/stop'));
assert.equal(describeTool('shell'),'Running a command');
const toolHistory=renderTimeline({startedAt:0,now:12000,events,models:['vendor/example-remote'],activity:{at:9500,tool:'shell',status:'completed',args:'private_argument'}});assert(toolHistory.includes('Last step: Running a command'));assert(!toolHistory.includes('private_argument'));
const p=mkdtempSync(tmpdir()+'/ui-trace-');process.env.OPENCODE_PROCESSING_DIR=p;
try{const {beginProcessing,endProcessing,processingDetails}=await import('/home/somdutta/.config/opencode/lib/processing-trace.mjs');const r=beginProcessing({session:'example',provider:'local',model:'example-model',now:1000});assert.deepEqual(processingDetails('example',0).models,['example-model']);endProcessing(r,{now:2000});assert.deepEqual(processingDetails('example',0).models,[]);assert.deepEqual(processingDetails('example',3000).events,[]);}finally{rmSync(p,{recursive:true,force:true})}
console.log('PASS budget values, generic model labels, observed tool stage, compact blocks, final history and stale-turn isolation');
console.log(renderTimeline({startedAt:0,now:12000,events,models:['vendor/example-remote']}));
