// Learned HA phrasings: when a Home Assistant request was answered by the cloud
// model instead of the local one, remember its token shape so the same wording
// routes locally next time.
import {readFileSync,writeFileSync,renameSync,mkdirSync,rmdirSync,statSync} from 'node:fs';
import {dirname} from 'node:path';
import {tokens} from './learning.js';

const read=path=>{
 try{const d=JSON.parse(readFileSync(path,'utf8'));return d&&Array.isArray(d.phrases)?d:{version:1,phrases:[]};}catch{return {version:1,phrases:[]};}
};

function locked(path,change){
 mkdirSync(dirname(path),{recursive:true,mode:0o700});
 const lock=path+'.lock';let held=false;
 for(let i=0;i<100;i++){
  try{mkdirSync(lock,{mode:0o700});held=true;break;}
  catch(e){if(e.code!=='EEXIST')throw e;try{if(Date.now()-statSync(lock).mtimeMs>15000)rmdirSync(lock);}catch{}}
 }
 if(!held)return false;
 try{
  const d=read(path);change(d);
  d.phrases=d.phrases.slice(-300);d.updatedAt=new Date().toISOString();
  const tmp=path+'.'+process.pid+'.tmp';
  writeFileSync(tmp,JSON.stringify(d,null,2)+'\n',{mode:0o600});renameSync(tmp,path);return true;
 }finally{try{rmdirSync(lock);}catch{}}
}

/** Remember "this wording is Home Assistant work, kind = history|devices". */
export function rememberPhrase(path,text,kind,inputs=[]){
 if(!text||!kind)return false;
 const t=tokens(text);
 const family=makeFamily(text,inputs);
 if(t.length<1)return false;
 return locked(path,d=>{
  const sameTokens=p=>p.tokens.length===t.length&&p.tokens.every((x,i)=>x===t[i]);
  const hit=d.phrases.find(p=>p.kind===kind&&sameTokens(p));
  const conflicting=d.phrases.filter(p=>p.kind!==kind&&sameTokens(p));
  if(conflicting.length){
   // The same wording was previously learned as a different kind. Do not stack a
   // second answer: mark all of them ambiguous so routing falls back to the
   // deterministic classifier instead of silently using whichever row came first.
   for(const row of conflicting){row.ambiguous=true;row.conflictKinds=[...new Set([...(row.conflictKinds||[]),kind])];row.ambiguousAt=new Date().toISOString();}
   if(hit){hit.ambiguous=true;hit.conflictKinds=[...new Set([...(hit.conflictKinds||[]),...conflicting.map(p=>p.kind)])];hit.ambiguousAt=new Date().toISOString();}
   return true;
  }
  if(hit){if(family)hit.family=family;hit.count=(hit.count||1)+1;hit.lastSeenAt=new Date().toISOString();}
  else d.phrases.push({version:1,tokens:t,kind,family,count:1,example:text.slice(0,160),createdAt:new Date().toISOString()});
  return true;
 });
}

// Families select a model only. They never reuse tool arguments or authorize writes.
const normalize=text=>text.normalize('NFKC').toLowerCase().replace(/[’']/g,"'").replace(/^(?:please|kindly)\s+/,'').replace(/\b(?:switch|power)\s+(on|off)\b/g,'turn $1').replace(/\b(?:last|past)\b/g,'last').replace(/[^a-z0-9_ '\-]/g,' ').replace(/\s+/g,' ').trim();
const escape=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
function makeFamily(text,inputs){
 let source=normalize(text);const slots=[];
 for(const input of inputs){
  for(const key of ['name','area','floor','person','entity_id']){
   const values=Array.isArray(input?.[key])?input[key]:[input?.[key]];
   for(const value of values){if(typeof value==='string'&&normalize(value).length>1)slots.push(normalize(value));}
  }
 }
 for(const slot of [...new Set(slots)].sort((a,b)=>b.length-a.length))source=source.replace(new RegExp('(?<![a-z0-9_])'+escape(slot)+'(?![a-z0-9_])','g'),'ZZSLOTZZ');
 // Verified HA evidence also permits a room reference slot when HA uses a different alias.
 if(!source.includes('ZZSLOTZZ'))source=source.replace(/^(what is (?:the )?(?:status|state) (?:of|in|for) )(.+?)( (?:room|bedroom))$/, '$1ZZSLOTZZ$3');
 source=source.replace(/\b\d+\b(?=\s+(?:hours?|minutes?|days?)\b)/g,'ZZNUMZZ');
 if(!/ZZSLOTZZ|ZZNUMZZ/.test(source))return null;
 const anchors=source.replace(/ZZSLOTZZ|ZZNUMZZ/g,'').match(/[a-z_]+/g)||[];
 if(anchors.length<2||source.length>300)return null;
 return '^'+escape(source).replace(/ZZSLOTZZ/g,"[a-z0-9_][a-z0-9_ '\-]{0,70}").replace(/ZZNUMZZ/g,'[0-9]{1,3}')+'$';
}
export function findPhrase(path,text){
 if(/\b(?:news|stocks?|tickets?|code|script|plugin|routing|router|deepseek|video|footage)\b/i.test(text))return null;
 const t=tokens(text);if(t.length<1)return null;
 const rows=read(path).phrases,key=t.join(' ');
 const exact=rows.filter(p=>p.tokens.join(' ')===key);
 if(exact.length){
  // Conflicting kinds for identical wording are ambiguous, not "first row wins".
  if(new Set(exact.map(p=>p.kind)).size!==1||exact.some(p=>p.ambiguous))return null;
  const row=exact[0];
  return {kind:row.kind,count:row.count||1,match:'exact'};
 }
 if(/\b(?:not|never|don't|dont|instead|except|and|then|also|why|explain)\b/i.test(text))return null;
 const query=normalize(text);
 const matches=rows.filter(p=>!p.ambiguous&&(()=>{try{return p.family&&new RegExp(p.family).test(query)}catch{return false}})());
 const kinds=new Set(matches.map(p=>p.kind));
 return kinds.size===1?{kind:matches[0].kind,count:matches[0].count||1,match:'family'}:null;
}

/** Tool identity, not the server namespace, determines historical semantics. */
export function phraseKindForTool(tool,result={}){
 if(result?.isError||result?.error)return null;
 for(const text of [result?.output,...(Array.isArray(result?.content)?result.content:[]).map(c=>c.text)].filter(t=>typeof t==='string')){
  try{const d=JSON.parse(text);if(d.error||d.isError||d.logbook_error||d.data?.failed?.length)return null}catch{}
 }
 if(tool==='ha-history_get_visited_locations')return 'history';
 // History investigations are multi-step evidence work; they are not a phrase-level
 // routing shortcut and must not teach a single required tool.
 if(/^ha[-_]event[-_]history_/.test(tool))return null;
 if(/^ha[-_]history_(?:get_device_status|get_device_status_report|get_on_entities_with_context)$/.test(tool)||/^home[-_]assistant_/.test(tool))return 'devices';
 return null;
}
