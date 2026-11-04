import {referenceMemory} from '../lib/context-hygiene.mjs';
import {localModel} from '../lib/routing-policy.mjs';
import {findTemplate} from '../lib/execution-templates.mjs';
import {focusFromReferences} from '../lib/ha-focus.mjs';
import {readFileSync} from 'node:fs';
import {homedir} from 'node:os';
import {findPhrase,rememberPhrase,phraseKindForTool} from '../plugins/ha-mcp-routing/phrases.js';
import {classify,isMixedRequest,isHAFollowup} from '../plugins/ha-mcp-routing/index.js';
const TTL=30*60*1000;
const phrasePath=homedir()+'/.local/share/opencode/ha-router/learned-phrases.json';
export function planHA(text,prior,now=Date.now()){
 const recent=prior&&now-prior.at<TTL&&now>=prior.at;
 if(!recent&&(/^(?:please )?(?:turn|switch)(?: it| them| those| both)?(?: back)? (?:on|off)[.!?]*$/i.test(text)||/^(?:please )?(?:turn|switch) (?:on|off) (?:it|them|those|both)[.!?]*$/i.test(text)))return {kind:'devices',referenceFollowup:true,focusTargets:[],carry:null};
 const follow=recent&&isHAFollowup(text);
 const kind=classify(text)||(!isMixedRequest(text)&&findPhrase(phrasePath,text)?.kind);
 if(isMixedRequest(text)||(!kind&&!follow))return null;
 const both=/\bboth\b/i.test(text);
 const groups=(prior?.exchanges||[prior]).filter(Boolean).slice(both?-2:-1);
 const focusTargets=follow?[...new Map(groups.flatMap(g=>g.focusTargets||focusFromReferences(g.references)).map(t=>[JSON.stringify(t),t])).values()]:[];
 return {kind:kind||prior.kind||'devices',referenceFollowup:!!follow,focusTargets,carry:follow?{focusTargets,exchanges:groups.map(p=>({question:p.question,answer:p.answer,references:(p.references||[]).slice(-4).map(r=>({tool:String(r.tool||''),input:String(r.input||'')}))}))}:null};
}
export function rememberHA(question,reply,now=Date.now(),prior=null){
 const item={question,answer:reply.text,references:(reply.references||[]).slice(-6),focusTargets:focusFromReferences(reply.references)};
 if(!item.focusTargets.length&&/certified replay/.test(reply.text)){const t=findTemplate(question);if(t?.recipe.kind==='write'&&t.recipe.args?.name)item.focusTargets=[{name:t.recipe.args.name,domain:t.recipe.args.domain||[]}];}
 const valid=(reply.references||[]).map(r=>phraseKindForTool(r.tool)).filter(Boolean);
 const kind=classify(question)||reply.haKind||(valid.length&&valid.every(k=>k==='history')?'history':'devices');
 if(valid.length&&!isHAFollowup(question)&&!isMixedRequest(question)&&!/\b(?:route|switch|use)\s+(?:to\s+)?(?:deepseek|cloud|openrouter)\b/i.test(question))rememberPhrase(phrasePath,question,kind,(reply.references||[]).flatMap(r=>{try{return [JSON.parse(r.input)]}catch{return []}}));
 const recent=prior&&now-prior.at<TTL&&now>=prior.at;
 const exchanges=[...(recent?(prior.exchanges||[prior]):[]),item].slice(-2);
 return {at:now,kind,...item,exchanges};
}
async function api(path,body){
 const cfg=JSON.parse(readFileSync(homedir()+'/.config/opencode/service.json','utf8'));
 const res=await fetch('http://127.0.0.1:'+cfg.port+path,{method:'POST',headers:{'content-type':'application/json',authorization:'Basic '+Buffer.from('opencode:'+cfg.password).toString('base64')},body:JSON.stringify(body),signal:AbortSignal.timeout(5000)});
 if(!res.ok)throw new Error('Could not prepare HA context: '+res.status);
 return res.json();
}
export async function prepareHA(id,plan){
 await api('/api/session',{id,title:'Telegram HA request',agent:'telegram',metadata:{haContextKind:plan.kind,haReferenceFollowup:!!plan.referenceFollowup,haFocusTargets:plan.focusTargets||[]},model:localModel(),location:{directory:homedir()}});
 if(plan.carry)await api('/api/session/'+id+'/synthetic',{text:referenceMemory(plan.carry),description:'Recent HA reference data',resume:false});
}
