import {DatabaseSync} from 'node:sqlite';
import {homedir} from 'node:os';
const fmt=n=>n>=1000?(n/1000).toFixed(1)+'k':String(n);
export function readLiveTokens(session,since,{dbPath=homedir()+'/.local/share/opencode/opencode.db'}={}){
 if(!session)return {groups:[],pending:0};let db;
 try{
  db=new DatabaseSync(dbPath,{readOnly:true});
  const rows=db.prepare("SELECT json_extract(data,'$.model.providerID') provider,json_extract(data,'$.tokens') tokens,json_extract(data,'$.cost') cost FROM session_message WHERE session_id=? AND type='assistant' AND time_created>=?").all(session,since);
  const groups=new Map();let pending=0;
  for(const row of rows){if(!row.tokens){pending++;continue;}const t=JSON.parse(row.tokens),provider=row.provider||'unknown',g=groups.get(provider)||{provider,input:0,output:0,cached:0,reasoning:0,steps:0,peak:0,cost:0};
   const cached=Number(t.cache?.read||0),input=Number(t.input||0)+cached;
   g.input+=input;g.cached+=cached;g.output+=Number(t.output||0);g.reasoning+=Number(t.reasoning||0);g.steps++;g.peak=Math.max(g.peak,input);g.cost+=Number(row.cost||0);groups.set(provider,g);
  }
  return {groups:[...groups.values()],pending};
 }catch{return {groups:[],pending:0,unavailable:true};}finally{db?.close();}
}
export function formatLiveTokens(usage,{requests=[]}={}){
 const lines=(usage?.groups||[]).map(g=>{
  const label=g.provider==='openrouter'?'Cloud':['evo-agent','evo-vision','vllm'].includes(g.provider)?'Local':g.provider;
  return `${label} tokens: total in ${fmt(g.input)} · out ${fmt(g.output)}${g.reasoning?' · think '+fmt(g.reasoning):''} · cached ${fmt(g.cached)} · peak input ${fmt(g.peak)}${g.provider==='openrouter'?' · $'+g.cost.toFixed(5):''}`;
 });
 for(const r of requests){if(!Number.isFinite(r.inputTokens))continue;lines.push(`${r.provider==='remote'?'Cloud':'Local'} current ${r.inputTokenKind==='text-only'?'text input':'input'} ${r.provider==='remote'?'~':''}${fmt(r.inputTokens)}${r.provider==='remote'?' (local tokenizer)':''}; output pending`);}
 if(!lines.length)lines.push(usage?.unavailable?'Tokens: usage unavailable':'Tokens: awaiting provider usage');
 else if(usage?.pending&&!requests.length)lines.push('Current pass: provider usage pending');
 return lines.join('\n');
}
