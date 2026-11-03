import test from 'node:test';import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import router from '/home/somdutta/.config/opencode/plugins/ha-mcp-routing/index.js';
import discovery from '/home/somdutta/.config/opencode/plugins/capability-discovery/index.js';
import {allowsTaskTool,assertDiscoveryPermission} from '/home/somdutta/.config/opencode/lib/tool-permissions.mjs';
import {captureTools,selectCapabilities,restoreSelected,availableCapabilities} from '/home/somdutta/.config/opencode/lib/capability-discovery.mjs';
import {runNativeText} from '/home/somdutta/.config/opencode/telegram/native-runner.mjs';
import {renderTimeline} from '/home/somdutta/.config/opencode/telegram/timeline.mjs';
const general=['discover_capabilities','inspect_resources','websearch','webfetch'];
const read='ha-history_get_device_status',history='ha-history_get_visited_locations',write='home-assistant_light__HassLightSet';
function fixture(state){
 const hooks=new Map(),tools=new Map(),sid='ses_permissions_'+randomUUID().replaceAll('-','');
 const register=(group,name,fn)=>{const key=group+':'+name;if(!hooks.has(key))hooks.set(key,[]);hooks.get(key).push(fn);};
 const ctx={options:{},storage:{get:async key=>key==='ha-turn:'+sid?state:undefined,set:async(key,v)=>{if(key==='ha-turn:'+sid)state=v},remove:async()=>{}},
  session:{hook:async(n,f)=>register('session',n,f),get:async()=>({agent:'telegram'}),switchModel:async()=>{}},
  permission:{hook:async(n,f)=>register('permission',n,f),assert:async()=>{}},
  tool:{hook:async(n,f)=>register('tool',n,f),transform:async fn=>fn({add:t=>tools.set(t.name,t)}),list:async()=>[...tools.values()].map(t=>({...t,id:t.name}))}};
 return {ctx,sid,tools,state:()=>state,run:async(group,name,event)=>{for(const fn of hooks.get(group+':'+name)||[])await fn(event)}};
}
const state=(kind='devices')=>({kind,permissionKind:kind,fastStatus:kind==='devices',requestText:'Read device status',startedAt:Date.now(),cloudStartedAt:Date.now(),calls:0,failures:0,fulfilled:false});
for(const kind of ['devices','history'])test('read-only discovery/web permission in '+kind,()=>{for(const t of general)assert.ok(allowsTaskTool(t,state(kind)));assert.ok(allowsTaskTool('shell',state(kind)));assert.ok(allowsTaskTool('read',state(kind)));for(const t of ['write','edit'])assert.equal(allowsTaskTool(t,state(kind)),false);});
test('targeted device writes cannot pass a known read-only task',()=>{assert.equal(allowsTaskTool(write,state()),false);assert.equal(allowsTaskTool(write,{...state(),fastStatus:false,requestText:'Turn on the kitchen light'}),true);});
test('cloud retains full native tool availability and does not inherit inferred local flags',()=>{for(const t of ['shell','read','write','edit',write,...general])assert.equal(allowsTaskTool(t,{...state('history'),kind:'fallback'}),true);assert.equal(allowsTaskTool(write,{...state(),kind:'fallback',requestText:'Read only; do not change anything'}),false);});
test('role revocation and task restrictions cannot be undone through discovery',()=>{
 const id='ses_selection_'+randomUUID();captureTools(id,{shell:{},[read]:{}},{replace:true});selectCapabilities(id,['shell']);
 captureTools(id,{[read]:{}},{replace:true});const out={};restoreSelected(id,out);assert.ok(!out.shell);
 captureTools(id,{shell:{},[read]:{}},{replace:true,allows:n=>n===read});assert.deepEqual(selectCapabilities(id,['shell','unknown',read]),{enabled:[read],unavailable:['shell','unknown'],note:'Enabled tools remain subject to native permissions and current user authorization. No operation has been executed.'});assert.deepEqual(availableCapabilities(id),[read]);
});
test('web search does not change the task permission scope before approval',async()=>{const f=fixture(state());await router.setup(f.ctx);await f.run('tool','execute.before',{sessionID:f.sid,tool:'websearch',input:{query:'public information'}});assert.equal(f.state().kind,'devices');assert.equal(f.state().fulfilled,false);await f.run('tool','execute.before',{sessionID:f.sid,tool:'shell',input:{command:'test'}});assert.equal(f.state().kind,'devices');});
test('permission evaluation preserves native allow, ask and deny',async()=>{
 const f=fixture(state());await router.setup(f.ctx);
 for(const effect of ['allow','ask','deny'])for(const action of general){const e={sessionID:f.sid,action,effect,source:{type:'tool'}};await f.run('permission','evaluate',e);assert.equal(e.effect,effect);}
 const unrelated={sessionID:f.sid,action:'provider.use',effect:'ask',source:{type:'integration'}};await f.run('permission','evaluate',unrelated);assert.equal(unrelated.effect,'ask');
});
test('the execution gate and permission hook agree for local and cloud',async()=>{
 for(const cloud of [false,true]){const f=fixture({...state(),kind:cloud?'fallback':'devices'});await router.setup(f.ctx);
  for(const tool of [...general,read,history,write,'shell','read','edit']){const permitted=allowsTaskTool(tool,f.state());const e={sessionID:f.sid,tool,input:{name:'Example device',domain:['light']}};
   if(permitted)await f.run('tool','execute.before',e);else await assert.rejects(f.run('tool','execute.before',e));
   const p={sessionID:f.sid,action:tool,effect:'ask',source:{type:'tool'}};await f.run('permission','evaluate',p);assert.equal(p.effect,permitted?'ask':'deny');
  }
 }
});
test('selected history stays available without turning a local task into an unrestricted one',async()=>{
 const f=fixture({...state(),requiredTool:read});await router.setup(f.ctx);
 const definitions=Object.fromEntries([...general,read,history,write,'shell'].map(n=>[n,{}]));
 const context={sessionID:f.sid,tools:{...definitions},system:[],options:{},model:{providerID:'evo-agent'}};await f.run('session','context',context);
 assert.equal(context.tools[write],undefined);selectCapabilities(f.sid,[history]);
 const next={...context,tools:{...definitions},system:[]};await f.run('session','context',next);assert.equal(f.state().kind,'devices');assert.ok(next.tools.shell);
 const event={sessionID:f.sid,kind:'primary',model:{providerID:'evo-agent'},request:new Request('http://localhost/chat',{method:'POST',body:JSON.stringify({messages:[{role:'user',content:'Read device status'}],tools:Object.keys(next.tools).map(n=>({type:'function',function:{name:n}}))})})};
 await f.run('session','http.request',event);assert.ok((await event.request.json()).tools.some(t=>t.function.name===history));
});
test('custom discovery checks native authorization before catalog access',async()=>{
 const f=fixture();let calls=0;f.ctx.tool.list=async()=>{calls++;return []};f.ctx.permission.assert=async()=>{throw Error('Native permission denied')};await discovery.setup(f.ctx);
 const context={sessionID:f.sid,signal:new AbortController().signal};
 await assert.rejects(f.tools.get('discover_capabilities').execute({},context),/Native permission denied/);assert.equal(calls,0);
 await assert.rejects(f.tools.get('inspect_resources').execute({adapter:'home-assistant'},context),/Native permission denied/);
});
test('native approval completes before any catalog read; no implicit approval is sent',async()=>{
 const f=fixture();let approve,reads=0;f.ctx.permission.assert=()=>new Promise(resolve=>approve=resolve);f.ctx.tool.list=async()=>{reads++;return []};await discovery.setup(f.ctx);
 const p=f.tools.get('discover_capabilities').execute({},{sessionID:f.sid,signal:new AbortController().signal});await new Promise(r=>setImmediate(r));assert.equal(reads,0);approve();await p;assert.equal(reads,1);
});
test('missing native permission service and cancelled requests fail closed',async()=>{
 await assert.rejects(assertDiscoveryPermission({},'discover_capabilities',{},{sessionID:'s'}),/unavailable/);
 const c=new AbortController();c.abort();await assert.rejects(assertDiscoveryPermission({permission:{assert:async()=>{}}},'discover_capabilities',{},{sessionID:'s',signal:c.signal}),/cancelled/);
});
test('Telegram reports pending native approval without replying to it',async()=>{
 let polls=0;const activity=[],calls=[],at=Date.now()+10;
 const api=async(path,method='GET')=>{calls.push({path,method});if(method!=='GET')return {};
  if(path.endsWith('/permission'))return [{id:'pending',action:'read'}];
  if(path.endsWith('/message')){polls++;return [{id:'u',type:'user',text:'test',time:{created:at}},...(polls>1?[{id:'a',type:'assistant',finish:'stop',content:[{type:'text',text:'Done'}],time:{created:at+1,completed:at+2}}]:[])];}
  return {time:{busy:at,idle:polls>1?at+3:0}};
 };
 const result=await runNativeText('ses_mock_approval','test',{model:'evo-agent/qwen36-agent',api,onActivity:a=>activity.push(a)});assert.ok(result.ok);assert.ok(activity.some(a=>a.status==='approval-required'));assert.ok(!calls.some(c=>c.path.endsWith('/reply')));
 const text=renderTimeline({startedAt:at-10,now:at+100,activity:{status:'approval-required',action:'read',at},events:[]});assert.match(text,/Awaiting your approval/);
});
