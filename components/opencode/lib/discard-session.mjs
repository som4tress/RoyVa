let DatabaseSync;
try{({DatabaseSync}=await import('node:sqlite'));}catch{
 const {Database}=await import('bun:sqlite');DatabaseSync=class extends Database {constructor(path,options={}){super(path,{readonly:!!options.readOnly});}};
}
import {readFileSync,writeFileSync,renameSync,readdirSync,rmSync,existsSync,lstatSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {homedir} from 'node:os';
import {randomUUID} from 'node:crypto';
import {isDiscarded,markDiscarded,validateSession,sessionHash} from '/home/somdutta/Projects/agent-learning/src/discard.mjs';
import {forgetSessionMemory} from './session-lifecycle.mjs';
import {scrub} from './procedure-memory.mjs';
const home=homedir(),base=join(home,'.local/share/opencode');
const normal=s=>String(s).normalize('NFKC').toLowerCase().trim().replace(/^["']|["']$/g,'').replace(/[.!?]+$/g,'').replace(/\s+/g,' ');
const atomic=(p,s)=>{const tmp=p+'.'+randomUUID();writeFileSync(tmp,s,{mode:0o600});renameSync(tmp,p);};
export async function nativeSessionRequest(id,operation='',method='POST',body){
 const service=JSON.parse(readFileSync(join(home,'.config/opencode/service.json'),'utf8'));
 return fetch(`http://127.0.0.1:${service.port}/api/session/${encodeURIComponent(validateSession(id))}${operation?'/'+operation:''}`,{method,headers:{'content-type':'application/json',authorization:'Basic '+Buffer.from('opencode:'+service.password).toString('base64')},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(20000)});
}
export async function discardSession(id,{dataRoot=base,dbPath=join(base,'opencode.db'),request=nativeSessionRequest,markerOptions}={}){
 validateSession(id);let db=new DatabaseSync(dbPath,{readOnly:true});const ids=[id],prompts=new Set(),artifacts=new Set(),blobs=new Set();
 const escapedRoot=dataRoot.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
 const artifactPattern=new RegExp(escapedRoot+'/(?:tool-output|fetched-sources|cloud-context/(?:evidence-v1|sources))/[A-Za-z0-9_.-]+','g');
 try{
  for(let i=0;i<ids.length;i++)for(const row of db.prepare('SELECT id FROM session_v2 WHERE parent_id=?').all(ids[i]))if(!ids.includes(row.id))ids.push(row.id);
  for(const sid of ids){
   for(const row of db.prepare('SELECT data FROM session_message WHERE session_id=?').all(sid)){
    const d=JSON.parse(row.data);if(d.text){prompts.add(normal(d.text));prompts.add(normal(scrub(d.text)));}
    for(const m of row.data.matchAll(artifactPattern))artifacts.add(m[0]);
   }
   for(const row of db.prepare('SELECT hash FROM blob_ref WHERE session_id=?').all(sid))blobs.add(row.hash);
  }
 }finally{db.close();}
 const set=new Set(ids);for(const sid of ids)markDiscarded(sid,markerOptions);
 let apiKey=process.env.VLLM_API_KEY;
 if(!apiKey)try{apiKey=readFileSync(join(home,'llm-server/api.env'),'utf8').match(/^VLLM_API_KEY=(.*)$/m)?.[1]?.replace(/^['"]|['"]$/g,'')}catch{}
 if(dataRoot===base&&apiKey)for(const sid of ids)await fetch('http://127.0.0.1:8011/discard-session',{method:'POST',headers:{'content-type':'application/json',authorization:'Bearer '+apiKey},body:JSON.stringify({sessionID:sid}),signal:AbortSignal.timeout(5000)}).catch(()=>{});
 // Block reuse before cancellation/deletion, including concurrent retries.
 await request(id,'interrupt').catch(()=>{});
 for(const sid of ids)await forgetSessionMemory(sid);
 const response=await request(id,'','DELETE');
 if(!response.ok&&response.status!==404)throw new Error('Rejected context is blocked, but native session deletion failed. Retry 👎 to finish deletion.');
 const matchesPrompt=value=>{const s=normal(value);return prompts.has(s)||s.length>=80&&[...prompts].some(p=>p.startsWith(s));};
 const touches=value=>{
  if(!value||typeof value!=='object')return false;
  if(Array.isArray(value))return value.some(touches);
  return Object.entries(value).some(([k,v])=>typeof v==='string'&&((/^(?:sessionID|sessionId|session_id|excludeSession)$/.test(k)&&set.has(v))||/^(?:task|query|example|requestText)$/.test(k)&&matchesPrompt(v))||v&&typeof v==='object'&&touches(v));
 };
 const prune=v=>{
  if(Array.isArray(v))return v.filter(x=>!touches(x)).map(prune);
  if(v&&typeof v==='object')return Object.fromEntries(Object.entries(v).map(([k,x])=>[k,prune(x)]));return v;
 };
 let removed=0;
 function sweep(folder){
  if(!existsSync(folder))return;
  for(const entry of readdirSync(folder,{withFileTypes:true})){
   const p=join(folder,entry.name);if(entry.isSymbolicLink())continue;if(entry.isDirectory()){sweep(p);continue;}
   if(!/\.jsonl?$/.test(p))continue;
   if(p.endsWith('.jsonl')){
    const lines=readFileSync(p,'utf8').split('\n').filter(Boolean),keep=lines.filter(line=>{try{return !touches(JSON.parse(line))}catch{return !ids.some(s=>line.includes(s));}});
    if(keep.length!==lines.length){atomic(p,keep.join('\n')+(keep.length?'\n':''));removed+=lines.length-keep.length;}
   }else{
    let value;try{value=JSON.parse(readFileSync(p,'utf8'))}catch{continue;}
    // Container indexes retain unrelated entries; standalone derived records do not.
    if(!Array.isArray(value)&&!['entries','templates','routes','phrases'].some(k=>Array.isArray(value[k]))&&touches(value)){rmSync(p);removed++;}
    else {const next=prune(value);if(JSON.stringify(next)!==JSON.stringify(value)){atomic(p,JSON.stringify(next));removed++;}}
   }
  }
 }
 // Delete private provider payload copies by their ownership metadata, not filenames supplied by a model.
 const payloadRoot=join(dataRoot,'cloud-context/payloads'),index=join(payloadRoot,'index.jsonl');
 if(existsSync(index)){
  const keep=[];for(const line of readFileSync(index,'utf8').split('\n').filter(Boolean)){
   let d;try{d=JSON.parse(line)}catch{keep.push(line);continue;}
   if(set.has(d.session)){
    if(/^[a-f0-9-]{36}$/.test(d.id)){rmSync(join(payloadRoot,d.id),{recursive:true,force:true});removed++;}
   }else keep.push(line);
  }atomic(index,keep.join('\n')+(keep.length?'\n':''));
 }
 for(const n of ['task-learning','procedures','ha-router','context-hygiene'])sweep(join(dataRoot,n));
 if(dataRoot===base)sweep(join(home,'.local/share/agent-learning/events'));
 // Other provider audit logs carry session keys; no source payloads are walked here.
 for(const name of ['audit.jsonl']){
  const p=join(dataRoot,'cloud-context',name);if(existsSync(p)){const lines=readFileSync(p,'utf8').split('\n').filter(Boolean);atomic(p,lines.filter(x=>{try{const d=JSON.parse(x);return !set.has(d.session)&&!set.has(d.sessionID)}catch{return true}}).join('\n')+'\n');}
 }
 db=new DatabaseSync(dbPath);
 try{
  db.exec('PRAGMA busy_timeout=5000; PRAGMA secure_delete=ON; BEGIN IMMEDIATE');
  for(const sid of ids){
   for(const {key,value} of db.prepare('SELECT key,value FROM kv').all())if(key.includes(sid)||value?.includes(sid))db.prepare('DELETE FROM kv WHERE key=?').run(key);
   db.prepare('DELETE FROM event WHERE aggregate_id=?').run(sid);
  }
  for(const hash of blobs)if(!db.prepare('SELECT 1 FROM blob_ref WHERE hash=? LIMIT 1').get(hash))db.prepare('DELETE FROM blob WHERE hash=?').run(hash);
  db.exec('COMMIT');
  for(const p of artifacts){
   // Keep shared source snapshots still referenced by another session. Never delete user project files.
   if(resolve(p).startsWith(resolve(dataRoot)+'/')&&!db.prepare('SELECT 1 FROM session_message WHERE instr(data,?)>0 LIMIT 1').get(p)){
    if(existsSync(p)&&lstatSync(p).isFile()){rmSync(p);removed++;}
   }
  }
  for(const sid of ids){if(db.prepare('SELECT 1 FROM session_v2 WHERE id=?').get(sid))throw new Error('Session deletion is unconfirmed.');}
 }finally{db.close();}
 for(const sid of ids){
  for(const p of [join(home,'.local/state/opencode/processing',sessionHash(sid)+'.json'),join(dataRoot,'task-learning/traces',sessionHash(sid)+'.json')])rmSync(p,{force:true});
 }
 return {discarded:true,sessions:ids.length,removedRuntimeRecords:removed};
}
export {isDiscarded};
