import {loadIndex} from './procedure-memory.mjs';
import {readFileSync,writeFileSync,mkdirSync,renameSync} from 'node:fs';
import {homedir} from 'node:os';
import {runProcedure,saveTemplate,decodeResult} from './execution-templates.mjs';
const root=homedir()+'/.local/share/opencode/ha-router',path=root+'/entity-aliases.json';
const normalizeTarget=s=>String(s).replace(/\blights\b/g,'light').replace(/\bswitches\b/g,'switch').replace(/\bfans\b/g,'fan');
const read=()=>{try{return JSON.parse(readFileSync(path,'utf8'))}catch{return {version:1,aliases:{}}}};
export function actionTarget(text){const s=String(text).trim().replace(/^["']|["']$/g,'').replace(/[.!?]+$/,'').replace(/^(?:please )?(?:use|route to|switch to) (?:deepseek|cloud|openrouter)\s*[:,\-]?\s*/i,'').toLowerCase();const m=s.match(/^(?:please )?(?:turn|switch) (?:on|off) (.+)$/)||s.match(/^(?:please )?(?:turn|switch) (.+) (?:on|off)$/);if(!m||/\b(it|them|those|both|all|every|and|then|not|never|my|our|back|again)\b/.test(m[1]))return null;return normalizeTarget(m[1].trim());}
export function knownAlias(text){
 const target=actionTarget(text);if(!target)return null;
 const options=Object.entries(read().aliases).filter(([k])=>normalizeTarget(k)===target).map(([,v])=>v);const entry=new Set(options.map(v=>v.entityID||v.name)).size===1?options.at(-1):null;if(entry&&Date.now()-entry.at<30*86400000)return entry;
 const refs=loadIndex().entries.filter(e=>/HassTurn(?:On|Off)$/.test(e.tool)&&actionTarget(e.task)===target&&e.args?.name&&Date.now()-Date.parse(e.lastUsed)<30*86400000);
 const names=[...new Set(refs.map(e=>e.args.name))];if(names.length!==1)return null;
 const ref=refs.at(-1);return {name:ref.args.name,domain:ref.args.domain,source:'previous successful tool reference'};
}
export async function validateAlias(alias){
 const remote=JSON.parse(readFileSync(homedir()+'/llm-server/ha-remote.json','utf8'));const base=new URL(remote.url).origin;
 const response=await fetch(base+'/api/states',{headers:{authorization:'Bearer '+process.env.HA_TOKEN},signal:AbortSignal.timeout(5000)});
 if(!response.ok)throw new Error('Cannot validate remembered device identity.');
 if(/linux|server|nuc|\bpc\b|computer|workstation|\bbox\b/i.test(alias.name))throw new Error('Computer/server power is excluded from learned device actions.');
 const rows=(await response.json()).filter(r=>String(r.attributes?.friendly_name||'').toLowerCase()===String(alias.name).toLowerCase()&&(!alias.domain?.length||alias.domain.includes(r.entity_id.split('.')[0])));
 if(rows.length!==1||alias.entityID&&rows[0].entity_id!==alias.entityID)throw new Error('Remembered target changed or is ambiguous; resolve it again.');
 return {name:rows[0].attributes.friendly_name,domain:[rows[0].entity_id.split('.')[0]]};
}
export async function learnAction(text,tool,args,result){
 if(!/HassTurn(?:On|Off)$/.test(tool)||!actionTarget(text))return false;
 const data=decodeResult(result);if(!data)return false;
 const successes=data.data?.success||[];if(successes.length===1&&!data.data?.failed?.length&&successes[0].name&&successes[0].id)args={name:successes[0].name,domain:[successes[0].id.split('.')[0]]};
 const cert=await runProcedure({operation:'certify',query:String(text).trim().replace(/^["']|["']$/g,''),tool,args,data},{timeoutMs:2000});
 if(!cert.ok||!cert.recipe)return false;
 saveTemplate(text,cert.recipe);
 const d=read();d.aliases[actionTarget(text)]={...cert.recipe.args,entityID:cert.recipe.expected_entities?.[0],at:Date.now()};
 mkdirSync(root,{recursive:true,mode:0o700});const temp=path+'.'+process.pid;writeFileSync(temp,JSON.stringify(d),{mode:0o600});renameSync(temp,path);return true;
}
