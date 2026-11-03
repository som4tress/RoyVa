import {readFileSync} from 'node:fs';import {homedir} from 'node:os';
const home=homedir();
for(const name of ['api.env','opencode.env','ha.env'])for(const line of readFileSync(home+'/llm-server/'+name,'utf8').split('\n')){if(!line.includes('='))continue;const at=line.indexOf('=');process.env[line.slice(0,at)]=line.slice(at+1).replace(/^"|"$/g,'');}
const unit=readFileSync(home+'/.config/systemd/user/opencode-telegram.service','utf8');process.env.OPENCODE_TG_MODEL=unit.match(/^Environment=OPENCODE_TG_MODEL=(.+)$/m)[1];process.env.OPENCODE_TG_BIN=home+'/.opencode/bin/opencode';
const {runOpenCode}=await import(home+'/.config/opencode/telegram/bridge.mjs');
for(const [tag,query,model] of [['free','Reply exactly: bridge working.',process.env.OPENCODE_TG_MODEL],['paid','Reply exactly: usage check.','openrouter/deepseek/deepseek-v4.1-flash-1017'],['local','Where is Shivangsh','evo-agent/qwen36-agent']]){
 const start=Date.now();const r=await runOpenCode('ses_review_'+tag+'_'+Date.now().toString(36),query,{model,timeout:45000});
 console.log(JSON.stringify({tag,configuredModel:model,ok:r.ok,seconds:Math.round((Date.now()-start)/10)/100,text:r.text.slice(0,260)}));
}
