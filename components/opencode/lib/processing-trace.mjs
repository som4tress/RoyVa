import {mkdirSync,writeFileSync,renameSync,readFileSync} from 'node:fs';import {homedir} from 'node:os';import {join} from 'node:path';import {createHash,randomUUID} from 'node:crypto';
const root=process.env.OPENCODE_PROCESSING_DIR||join(homedir(),'.local/state/opencode/processing');
const states=new Map();const path=s=>join(root,createHash('sha256').update(s).digest('hex')+'.json');
function save(session,state){try{mkdirSync(root,{recursive:true,mode:0o700});const file=path(session),temp=file+'.'+process.pid;writeFileSync(temp,JSON.stringify({pid:process.pid,...state}),{mode:0o600});renameSync(temp,file);}catch{}}
export function beginProcessing({session,provider,model,inputTokens,inputTokenKind,kind='primary',now=Date.now()}){
 if(!session||kind!=='primary')return null;
 const id=randomUUID();let state=states.get(session);if(!state){state={active:{},events:[]};states.set(session,state);if(states.size>1000){const idle=[...states].find(([,s])=>!Object.keys(s.active).length);if(idle)states.delete(idle[0]);}}
 state.active[id]={provider:provider==='remote'?'remote':'local',model:String(model).slice(0,100),inputTokens:Number.isFinite(inputTokens)?inputTokens:undefined,inputTokenKind,at:now};mark(session,state,now);return {session,id};
}
function mark(session,state,at){const active=Object.values(state.active),providers=new Set(active.map(x=>x.provider)),phase=providers.size>1?'both':providers.has('remote')?'remote':providers.has('local')?'local':'other';state.events.push({at,phase,models:[...new Set(active.map(x=>x.model))]});state.events=state.events.slice(-256);save(session,state);}
export function endProcessing(ref,{now=Date.now()}={}){if(!ref)return;const state=states.get(ref.session);if(!state?.active[ref.id])return;delete state.active[ref.id];mark(ref.session,state,now);}
export function processingDetails(session,since){
 if(!session)return {events:[],models:[]};
 try{const state=JSON.parse(readFileSync(path(session),'utf8'));process.kill(state.pid,0);const requests=Object.values(state.active).filter(x=>x.at>=since);return {events:state.events.filter(e=>e.at>=since&&['local','remote','both','other'].includes(e.phase)),models:[...new Set(requests.map(x=>x.model))],requests};}catch{return {events:[],models:[],requests:[]};}
}
export function processingEvents(session,since){return processingDetails(session,since).events;}
