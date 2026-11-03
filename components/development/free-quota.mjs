import {readFileSync,writeFileSync,renameSync,mkdirSync} from 'node:fs';
import {homedir} from 'node:os';import {dirname} from 'node:path';
export const FREE_QUOTA=homedir()+'/.local/state/opencode/free-model-quota.json';
export const PAID_MODEL='openrouter/deepseek/deepseek-v4.1-flash-1017';
export function quotaInfo(error){
 let limit=false,retryAfterMs=null;
 function walk(value,depth=0){
  if(depth>7||value==null)return;
  if(typeof value==='string'){
   if(/free[ ._-]*(?:usage[ ._-]*)?limit|FreeUsageLimitError/i.test(value))limit=true;
   try{walk(JSON.parse(value),depth+1)}catch{}return;
  }
  if(typeof value==='object')for(const [key,item] of Object.entries(value)){
   if(key==='retryAfterMs'&&Number.isFinite(Number(item)))retryAfterMs=Number(item);
   else walk(item,depth+1);
  }
 }
 walk(error);return limit?{retryAfterMs}:null;
}
export function freeQuotaState(path=FREE_QUOTA){try{return JSON.parse(readFileSync(path,'utf8'))}catch{return {until:0}}}
export function isFreeCoolingDown(path=FREE_QUOTA,now=Date.now()){return Number(freeQuotaState(path).until)>now;}
export function recordFreeQuota(error,{path=FREE_QUOTA,now=Date.now()}={}){
 const info=quotaInfo(error);if(!info)return false;
 const delay=Math.max(60000,Math.min(24*3600000,info.retryAfterMs||300000));
 const until=Math.max(Number(freeQuotaState(path).until)||0,now+delay);
 mkdirSync(dirname(path),{recursive:true,mode:0o700});const temp=path+'.'+process.pid+'.tmp';writeFileSync(temp,JSON.stringify({until,reason:'provider-free-limit',recordedAt:now}),{mode:0o600});renameSync(temp,path);return true;
}
