import {readFileSync} from 'node:fs';import {homedir} from 'node:os';
const home=homedir();for(const name of ['api.env','opencode.env','ha.env'])for(const line of readFileSync(home+'/llm-server/'+name,'utf8').split('\n')){const at=line.indexOf('=');if(at>0)process.env[line.slice(0,at)]=line.slice(at+1).replace(/^"|"$/g,'');}
delete process.env.OPENCODE_TG_MODEL;process.env.OPENCODE_TG_BIN=home+'/.opencode/bin/opencode';
const {runOpenCode}=await import(home+'/.config/opencode/telegram/bridge.mjs');
const before=await(await fetch('http://127.0.0.1:8011/metrics')).json();const start=Date.now();
const result=await runOpenCode('ses_review_ha_default_'+Date.now().toString(36),'Where is Shivangsh',{timeout:15000});
const after=await(await fetch('http://127.0.0.1:8011/metrics')).json();
console.log(JSON.stringify({ok:result.ok,seconds:(Date.now()-start)/1000,configuredGeneralModel:JSON.parse(readFileSync(home+'/.config/opencode/opencode.json','utf8')).model,modelCalls:after.upstream-before.upstream,templateHits:after.templateHits-before.templateHits,paidFooter:result.text.includes('Usage:')}));
if(!result.ok||after.templateHits-before.templateHits!==1||after.upstream!==before.upstream)process.exitCode=1;
