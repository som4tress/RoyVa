import {readFileSync} from 'node:fs';import {homedir} from 'node:os';
const home=homedir();for(const name of ['api.env','opencode.env','ha.env'])for(const line of readFileSync(home+'/llm-server/'+name,'utf8').split('\n')){const at=line.indexOf('=');if(at>0)process.env[line.slice(0,at)]=line.slice(at+1).replace(/^"|"$/g,'');}
delete process.env.OPENCODE_TG_MODEL;process.env.OPENCODE_TG_BIN=home+'/.opencode/bin/opencode';
const {runOpenCode}=await import(home+'/.config/opencode/telegram/bridge.mjs');
for(const [name,query] of [['quota','Reply exactly: fallback recovered.'],['history','Shobha location history in the last one hour'],['devices','What switches and devices are on right now'],['explicit',"I want Shobha's location history in the last hour - route to DeepSeek"]]){
 const start=Date.now();const result=await runOpenCode('ses_history_fix_'+name+'_'+Date.now().toString(36),query,{timeout:60000});
 console.log(JSON.stringify({name,ok:result.ok,seconds:Math.round((Date.now()-start)/10)/100,text:result.text.slice(0,450)}));
 if(!result.ok)process.exitCode=1;
}
