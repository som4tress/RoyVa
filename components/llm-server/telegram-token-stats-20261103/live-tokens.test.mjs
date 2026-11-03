import test from 'node:test';import assert from 'node:assert/strict';import {DatabaseSync} from 'node:sqlite';import {mkdtempSync,rmSync} from 'node:fs';import {tmpdir} from 'node:os';
import {readLiveTokens,formatLiveTokens} from '/home/somdutta/.config/opencode/telegram/live-tokens.mjs';
import {renderTimeline} from '/home/somdutta/.config/opencode/telegram/timeline.mjs';
test('live totals exclude old turns and other sessions; pending usage is not invented',()=>{
 const root=mkdtempSync(tmpdir()+'/live-tokens-'),path=root+'/db';let db;
 try{db=new DatabaseSync(path);db.exec('create table session_message (session_id text,type text,time_created integer,data text)');const add=db.prepare('insert into session_message values (?,?,?,?)');
 for(const [sid,at,input,cached] of [['s',999,90000,0],['other',1001,80000,0],['s',1001,100,20],['s',1002,50,10]])add.run(sid,'assistant',at,JSON.stringify({model:{providerID:'evo-agent'},tokens:{input,output:5,cache:{read:cached}},cost:0}));
 add.run('s','assistant',1003,JSON.stringify({model:{providerID:'openrouter'}}));db.close();db=null;
 const r=readLiveTokens('s',1000,{dbPath:path});assert.equal(r.groups[0].input,180);assert.equal(r.groups[0].output,10);assert.equal(r.groups[0].peak,120);assert.equal(r.pending,1);
 const text=formatLiveTokens(r,{requests:[{provider:'remote',inputTokens:1250}]});assert.match(text,/Cloud current input ~1.3k \(local tokenizer\); output pending/);assert.ok(!text.includes('80000'));
 }finally{db?.close();rmSync(root,{recursive:true,force:true});}
});
test('missing usage is labeled unavailable and live stats appear in the progress body',()=>{
 const usage=formatLiveTokens({groups:[],pending:0,unavailable:true});assert.match(usage,/unavailable/);
 const t=renderTimeline({startedAt:1000,now:4000,events:[{at:1000,phase:'local',models:['qwen']}],tokenStats:'Local current input 5.3k; output pending'});assert.match(t,/Local current input/);assert.match(t,/Reply to steer/);
});
