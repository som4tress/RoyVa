import {mkdirSync,existsSync,writeFileSync,renameSync} from 'node:fs';
import {join} from 'node:path';
import {homedir} from 'node:os';
import {createHash,randomUUID} from 'node:crypto';
export const discardRoot=process.env.AGENT_DISCARD_HOME||join(homedir(),'.local/state/opencode/discarded-sessions');
export const sessionHash=id=>createHash('sha256').update(id).digest('hex');
export function validateSession(id){if(typeof id!=='string'||!/^ses_[a-zA-Z0-9_-]+$/.test(id))throw new Error('Invalid session ID');return id;}
export function isDiscarded(id,{path=discardRoot}={}){return typeof id==='string'&&/^ses_[a-zA-Z0-9_-]+$/.test(id)&&existsSync(join(path,sessionHash(id)+'.json'));}
export function markDiscarded(id,{path=discardRoot}={}){
 validateSession(id);mkdirSync(path,{recursive:true,mode:0o700});const file=join(path,sessionHash(id)+'.json');
 if(!existsSync(file)){const temp=file+'.'+randomUUID();writeFileSync(temp,JSON.stringify({version:1,rejectedAt:Date.now(),sessionHash:sessionHash(id)}),{mode:0o600});renameSync(temp,file);}
}
