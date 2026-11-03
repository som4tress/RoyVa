import test from 'node:test';import assert from 'node:assert/strict';import {DatabaseSync} from 'node:sqlite';import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,existsSync,rmSync} from 'node:fs';import {tmpdir} from 'node:os';
import {discardSession} from '/home/somdutta/.config/opencode/lib/discard-session.mjs';
import {isDiscarded} from '/home/somdutta/Projects/agent-learning/src/discard.mjs';
import {catalogPage,captureTools,selectCapabilities,restoreSelected,clearDiscovery} from '/home/somdutta/.config/opencode/lib/capability-discovery.mjs';
test('discard deletes parent/children and derived memories but preserves unrelated sessions and shared evidence',async()=>{
 const root=mkdtempSync(tmpdir()+'/discard-check-'),data=root+'/data',dbPath=root+'/db';mkdirSync(data+'/task-learning/records',{recursive:true});mkdirSync(data+'/procedures',{recursive:true});mkdirSync(data+'/tool-output',{recursive:true});
 const sid='ses_discard_unit',child='ses_discard_unit_child',healthy='ses_keep_unit';let db=new DatabaseSync(dbPath);
 db.exec('create table session_v2(id text,parent_id text);create table session_message(session_id text,data text);create table blob_ref(session_id text,hash text);create table blob(hash text);create table kv(key text,value text);create table event(aggregate_id text);');
 for(const [id,parent] of [[sid,null],[child,sid],[healthy,null]])db.prepare('insert into session_v2 values (?,?)').run(id,parent);
 const own=data+'/tool-output/own.txt',shared=data+'/tool-output/shared.txt';writeFileSync(own,'wrong context');writeFileSync(shared,'shared data');
 db.prepare('insert into session_message values (?,?)').run(sid,JSON.stringify({text:'Read alpha',paths:[own,shared]}));db.prepare('insert into session_message values (?,?)').run(healthy,JSON.stringify({text:'Read beta',path:shared}));db.prepare('insert into kv values (?,?)').run('plugin:ha-turn:'+sid,'bad');db.close();
 writeFileSync(data+'/task-learning/tasks.json',JSON.stringify({entries:[{task:'Read alpha',sessionID:healthy},{task:'Read beta',sessionID:healthy}]}));
 writeFileSync(data+'/procedures/archive.jsonl',JSON.stringify({sessionID:sid,task:'Read alpha'})+'\n'+JSON.stringify({sessionID:healthy,task:'Read beta'})+'\n');
 const request=async(id,op,method)=>{if(method==='DELETE'){const c=new DatabaseSync(dbPath);for(const s of [sid,child]){c.prepare('delete from session_v2 where id=?').run(s);c.prepare('delete from session_message where session_id=?').run(s);}c.close();}return {ok:true,status:204}};
 try{const r=await discardSession(sid,{dataRoot:data,dbPath,request,markerOptions:{path:root+'/markers'}});assert.equal(r.sessions,2);assert.ok(isDiscarded(sid,{path:root+'/markers'}));assert.ok(isDiscarded(child,{path:root+'/markers'}));assert.ok(!existsSync(own));assert.ok(existsSync(shared));assert.deepEqual(JSON.parse(readFileSync(data+'/task-learning/tasks.json')).entries.map(x=>x.task),['Read beta']);assert.ok(!readFileSync(data+'/procedures/archive.jsonl','utf8').includes(sid));const c=new DatabaseSync(dbPath);assert.equal(c.prepare('select count(*) n from session_v2').get().n,1);assert.equal(c.prepare('select count(*) n from kv').get().n,0);c.close();}finally{rmSync(root,{recursive:true,force:true});}
});
test('discovery paginates real schemas and cannot enable unobserved tools',()=>{
 const id='ses_catalog_unit';captureTools(id,{read:{a:1},websearch:{b:2}});
 const page=catalogPage([{id:'read',description:'Read files',input:{type:'object'}},{id:'websearch',description:'Search public web',input:{type:'object',required:['query']}}],{query:'weather',limit:1,schemas:true,available:['read','websearch']});assert.equal(page.total,2);assert.equal(page.partial,true);assert.equal(page.nextOffset,1);
 const selected=selectCapabilities(id,['websearch','privileged_unknown']);assert.deepEqual(selected.enabled,['websearch']);assert.deepEqual(selected.unavailable,['privileged_unknown']);const current={};restoreSelected(id,current);assert.ok(current.websearch);assert.ok(!current.privileged_unknown);clearDiscovery(id);
});
