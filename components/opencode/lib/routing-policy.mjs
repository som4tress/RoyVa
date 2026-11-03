import {readFileSync} from 'node:fs';import {homedir} from 'node:os';
const defaults={local:{providerID:'evo-agent',id:'qwen36-agent'},vision:{providerID:'evo-vision',id:'qwen35-vision'},cloud:{providerID:'openrouter',id:'deepseek/deepseek-v4.1-flash-1017'}};
export function routingPolicy(){try{return JSON.parse(readFileSync(process.env.OPENCODE_ROUTING_POLICY_FILE||homedir()+'/.config/opencode/routing-policy.json','utf8'))}catch{return {}}}
function model(name){const value=routingPolicy()[name];return value&&typeof value.providerID==='string'&&typeof value.id==='string'&&value.providerID&&value.id?{providerID:value.providerID,id:value.id}:defaults[name];}
export const cloudModel=()=>model('cloud');export const localModel=()=>model('local');export const visionModel=()=>model('vision');
export const cloudModelID=()=>{const m=cloudModel();return m.providerID+'/'+m.id;};

export function policyBudget(name,fallback){const n=Number(routingPolicy().budgets?.[name]);return Number.isFinite(n)&&n>=100&&n<=900000?n:fallback;}
