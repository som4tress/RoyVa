import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,mkdirSync,readFileSync,rmSync,statSync} from 'node:fs';
import {tmpdir} from 'node:os';import {join} from 'node:path';
import {rememberProcedure,recallProcedures,loadIndex,scrub} from '/home/somdutta/.config/opencode/lib/procedure-memory.mjs';
const dir=mkdtempSync(join(tmpdir(),'procedure-memory-test-'));const path=join(dir,'index.json');
try{
 const base={task:'Turn kitchen light on',tool:'home-assistant_intent__HassTurnOn',args:{name:'Kitchen Light'},result:{output:'{"success":true}'},sessionID:'first'};
 assert(rememberProcedure(base,path));assert(rememberProcedure(base,path));assert.equal(loadIndex(path).entries.length,1);assert.equal(loadIndex(path).entries[0].count,2);
 assert.equal(recallProcedures(base.task,{path,excludeSession:'next'}).length,1);
 assert.equal(recallProcedures('Turn kitchen light off',{path}).length,0);assert.equal(recallProcedures('Explain quantum physics',{path}).length,0);assert.equal(recallProcedures(base.task,{path,excludeSession:'first'}).length,0);
 assert(!rememberProcedure({...base,result:{isError:true}},path));assert(!rememberProcedure({...base,result:{output:'{"data":{"failed":[1]}}'}},path));
 const file=join(dir,'example.py');writeFileSync(file,'print(1)\n');assert(rememberProcedure({task:'Write a reusable weather script',tool:'write',args:{filePath:file,content:'private generated code'},sessionID:'code'},path));
 assert.equal(recallProcedures('Write a reusable weather script',{path}).length,1);writeFileSync(file,'print(2)\n');assert.equal(recallProcedures('Write a reusable weather script',{path}).length,0);
 assert.equal(scrub({password:'abc'}).password,'[not stored]');assert.equal(scrub('curl -H Authorization: Bearer secret'),'[sensitive value omitted]');
 process.env.TEST_MEMORY_SECRET='test-private-value';assert(!String(scrub('example test-private-value')).includes('test-private-value'));assert.equal(scrub('2026-10-31','date'),'[resolve fresh]');
 assert(!readFileSync(path,'utf8').includes('private generated code'));assert.equal(statSync(path).mode&0o777,0o600);
 console.log('PASS: automatic deduplication, selective recall, opposite-action separation, failed-tool rejection, file-change invalidation, secret/code redaction, fresh dates and private file permissions.');
}finally{rmSync(dir,{recursive:true,force:true})}
