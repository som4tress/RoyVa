import {readFileSync} from 'node:fs';import {homedir} from 'node:os';
const home=homedir();for(const name of ['api.env','opencode.env','ha.env'])for(const line of readFileSync(home+'/llm-server/'+name,'utf8').split('\n')){const at=line.indexOf('=');if(at>0)process.env[line.slice(0,at)]=line.slice(at+1).replace(/^"|"$/g,'');}
delete process.env.OPENCODE_TG_MODEL;process.env.OPENCODE_TG_BIN=home+'/.opencode/bin/opencode';const {runOpenCode}=await import(home+'/.config/opencode/telegram/bridge.mjs');
for(const [name,query] of [['repeat','Shobha location history in the last one hour'],['correction','When I am asking for shobha’s location history why am I getting her last location only']]){
 const start=Date.now();const r=await runOpenCode('ses_final_location_'+name+'_'+Date.now().toString(36),query,{timeout:45000});console.log(JSON.stringify({name,ok:r.ok,seconds:(Date.now()-start)/1000,hasMap:r.text.includes('maps.google'),text:r.text.slice(0,400)}));if(!r.ok||r.text.includes('maps.google'))process.exitCode=1;
}
