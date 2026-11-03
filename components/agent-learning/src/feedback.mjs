import {mkdirSync,readFileSync,writeFileSync,readdirSync,renameSync,existsSync} from 'node:fs';
import {join} from 'node:path';import {homedir} from 'node:os';import {createHash,randomUUID} from 'node:crypto';
import {isDiscarded} from './discard.mjs';
export const root=process.env.AGENT_LEARNING_HOME||join(homedir(),'.local/share/agent-learning');
const hash=x=>createHash('sha256').update(x).digest('hex');
const read=p=>{try{return JSON.parse(readFileSync(p,'utf8'))}catch{return null}};
function write(p,data){const tmp=p+'.'+randomUUID();writeFileSync(tmp,JSON.stringify(data),{mode:0o600});renameSync(tmp,p);}
const dir=(r,n)=>{const d=join(r,n);mkdirSync(d,{recursive:true,mode:0o700});return d};
export function emojiVote(text){const t=String(text).replace(/[\uFE0E\uFE0F\u{1F3FB}-\u{1F3FF}]/gu,'').trim();return t==='👍'?'accept':t==='👎'?'reject':null;}
export const HELP='Feedback: /feedback accept | reject <reason> | status. Defaults to the latest completed answer; use --message <OpenCode message ID> for an older answer, or reply to its Telegram message. 👍 or accept confirms the answer AND authorizes creating a reusable tool candidate. 👎 or reject discards the entire targeted session and its derived runtime context. No creation before confirmation; validation is required before activation.';
export function parseFeedback(text){
 let t=String(text).trim();const vote=emojiVote(t);if(vote)return {action:vote,note:''};
 if(!/^\/feedback(?:@\w+)?(?:\s|$)/i.test(t))return null;
 t=t.replace(/^\/feedback(?:@\w+)?\s*/i,'');let messageID;
 t=t.replace(/(?:^|\s)--message\s+(msg_[a-zA-Z0-9_-]+)/,(m,id)=>{messageID=id;return ' '}).trim();
 if(/--message\b/.test(t))return {action:'invalid',note:'Invalid --message selector; use an exact OpenCode message ID.'};
 const [action='help',...rest]=t.split(/\s+/);return {action:action.toLowerCase(),note:rest.join(' '),messageID};
}
export function completedTarget(messages,sessionID,messageID){
 const rows=messages.filter(m=>m.type==='assistant'&&m.content?.some(p=>p.type==='text'&&p.text?.trim())&&m.time?.completed&&!m.error&&!['error','length'].includes(m.finish));
 const m=messageID?rows.find(m=>m.id===messageID):rows.sort((a,b)=>b.time.completed-a.time.completed)[0];
 const text=m&&(m.content||[]).filter(p=>p.type==='text').map(p=>p.text).join('');
 if(!m||!text?.trim())throw new Error('No completed answer found. Specify an answer, not a pending task or tool call.');
 return {sessionID,messageID:m.id,digest:hash(text)};
}
function targetKey(t){if(!t||typeof t.sessionID!=='string'||!/^msg_[a-zA-Z0-9_-]+$/.test(t.messageID)||!/^[a-f0-9]{64}$/.test(t.digest))throw new Error('Invalid feedback target');return hash(t.sessionID+'|'+t.messageID+'|'+t.digest);}
export function status(target,{path=root}={}){
 if(isDiscarded(target.sessionID))return {acceptance:'reject',buildAllowed:false,latestEvent:null,events:0,activated:false,discarded:true};
 const key=targetKey(target),folder=dir(path,'events');let events=[];
 for(const f of readdirSync(folder)){if(!f.startsWith(key+'.'))continue;const e=read(join(folder,f));if(e)events.push(e);}
 const priority={accept:0,clear:2,reject:3,'revoke-build':4};events.sort((a,b)=>a.at-b.at||(priority[a.action]-priority[b.action])||a.id.localeCompare(b.id));
 const vote=events.filter(e=>['accept','reject','clear'].includes(e.action)).at(-1);
 const consent=events.filter(e=>['accept','revoke-build','reject','clear'].includes(e.action)).at(-1);
 return {acceptance:vote?.action||'unconfirmed',buildAllowed:vote?.action==='accept'&&consent?.action==='accept',latestEvent:events.at(-1)?.id||null,events:events.length,activated:false};
}
export function recordFeedback({target,action,actor,source,note='',eventID=randomUUID(),at=Date.now()},{path=root}={}){
 if(isDiscarded(target.sessionID)){if(action==='accept')throw new Error('This session was discarded. A new answer needs fresh approval.');return status(target,{path});}
 if(!['accept','reject','clear','revoke-build'].includes(action))throw new Error('Unknown feedback action');
 if(!actor||!source)throw new Error('Feedback requires an identified source and actor');
 const key=targetKey(target),p=join(dir(path,'events'),key+'.'+hash(source+'|'+eventID)+'.json');
 if(existsSync(p))return {...status(target,{path}),duplicate:true};

 const safeNote=/bearer\s|eyJ[A-Za-z0-9_-]{10,}\.|sk-[A-Za-z0-9_-]{8,}|password|token|secret|credential/i.test(note)?'[sensitive note omitted]':String(note).slice(0,500);
 write(p,{version:1,id:eventID,at,target,action,actor:String(actor).slice(0,150),source,note:safeNote});
 return status(target,{path});
}
export function receipt(action,s){
 if(action==='status')return `Acceptance: ${s.acceptance}. Tool-building consent: ${s.buildAllowed?'granted':'not granted'}. Feedback does not activate tools.`;
 if(action==='revoke-build')return 'Tool-building consent revoked for this answer.';
 if(action==='accept')return 'Answer accepted; permission to create a reusable tool candidate recorded. It must pass validation before activation.';
 return action==='clear'?'Acceptance withdrawn; tool-building consent is no longer valid.':s.discarded?'Rejected session discarded. Next message starts fresh; no remote retry or tool creation.':'Answer marked incorrect; tool-building consent blocked. Your feedback is saved.';
}
export function mapTelegram(chatId,messageIds,target,{path=root}={}){
 targetKey(target);const folder=dir(path,'telegram');for(const id of messageIds)write(join(folder,hash(String(chatId)+'|'+id)+'.json'),{chatId:String(chatId),messageId:id,target});
 write(join(folder,hash(String(chatId)+'|latest')+'.json'),{chatId:String(chatId),target});
}
export function telegramTarget(chatId,messageId,{path=root}={}){return read(join(dir(path,'telegram'),hash(String(chatId)+'|'+(messageId??'latest'))+'.json'))?.target||null;}
