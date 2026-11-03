import {readFileSync} from 'node:fs';import {homedir} from 'node:os';
const h=homedir(),cfg=JSON.parse(readFileSync(h+'/.config/opencode/service.json','utf8'));const headers={'content-type':'application/json',authorization:'Basic '+Buffer.from('opencode:'+cfg.password).toString('base64')};
export async function api(path,body){const r=await fetch('http://127.0.0.1:'+cfg.port+path,{method:body?'POST':'GET',headers,...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(10000)});if(!r.ok)throw new Error('OpenCode API '+r.status);return r.json();}
export async function httpAsk(text,{sessionID='ses_http_cache_'+Date.now().toString(36),timeout=90000}={}){
 await api('/api/session',{id:sessionID,title:'Cache self-test: '+text.slice(0,45),agent:'build',model:{providerID:'evo-agent',id:'qwen36-agent'},location:{directory:h}});
 const started=Date.now();await api('/api/session/'+sessionID+'/prompt',{text});
 while(Date.now()-started<timeout){const s=(await api('/api/session/'+sessionID)).data;if(s?.time?.idle>=s?.time?.busy&&s?.outcome){const messages=(await api('/api/session/'+sessionID+'/context')).data||[];const assistants=messages.filter(m=>m.type==='assistant');const last=assistants.at(-1);return {ok:s.outcome==='succeeded',text:(last?.content||[]).filter(p=>p.type==='text').map(p=>p.text).join('\n'),sessionId:sessionID,seconds:(Date.now()-started)/1000,outcome:s.outcome};}await new Promise(r=>setTimeout(r,1000));}
 await api('/api/session/'+sessionID+'/interrupt',{});return {ok:false,text:'Test timeout; interrupted diagnostic session',sessionId:sessionID,seconds:(Date.now()-started)/1000};
}
