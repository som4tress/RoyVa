from pathlib import Path
import json
h=Path.home();base=h/'.config/opencode';backup=h/'opencode-migration-backup/global-execution-adapters';backup.mkdir(exist_ok=True)
p=base/'lib/execution-templates.mjs';(backup/p.name).write_text(p.read_text());s=p.read_text().replace('mkdirSync,appendFileSync','mkdirSync,appendFileSync,existsSync')
s=s.replace("const LOOKUPS=new Set", "const EXTENSIONS=new Map(),EXTRA_FILES=new Set();\nexport function registerExecutionAdapter(adapter,modulePath){\n if(!adapter||typeof adapter.id!=='string'||!Array.isArray(adapter.tools)||!adapter.tools.length||typeof adapter.run!=='function'||typeof adapter.format!=='function')throw new Error('Invalid execution adapter');\n if(adapter.tools.some(t=>typeof t!=='string'||SUPPORTED.has(t)))throw new Error('Adapter tool conflicts with an existing adapter');\n for(const tool of adapter.tools){SUPPORTED.add(tool);EXTENSIONS.set(tool,adapter)}\n if(modulePath)EXTRA_FILES.add(modulePath);\n for(const file of adapter.fingerprintFiles||[])EXTRA_FILES.add(file.startsWith('/')?file:ROOT+'/'+file);\n}\nconst LOOKUPS=new Set")
old="FILES.map(p=>readFileSync(ROOT+'/'+p)).concat([readFileSync(homedir()+'/llm-server/ha-remote.json')])"
new="FILES.map(p=>readFileSync(ROOT+'/'+p)).concat([...EXTRA_FILES].map(p=>readFileSync(p)),[readFileSync(homedir()+'/llm-server/ha-remote.json'),existsSync(ROOT+'/execution-adapters.json')?readFileSync(ROOT+'/execution-adapters.json'):Buffer.from('{}')])"
assert old in s;s=s.replace(old,new)
s=s.replace(" if(!code||!SUPPORTED.has(recipe?.tool))return false;", " if(!code||!SUPPORTED.has(recipe?.tool)||!['read','write'].includes(recipe.kind))return false;\n const adapter=EXTENSIONS.get(recipe.tool);if(adapter&&(recipe.adapter!==adapter.id||((adapter.writeTools||[]).includes(recipe.tool)!==(recipe.kind==='write'))))return false;")
s=s.replace(" if(turn.calls.some(c=>c.id!==call.id&&!LOOKUPS.has(c.function?.name)))return null;", " const adapter=EXTENSIONS.get(call.function.name),lookups=adapter?new Set(adapter.lookupTools||[]):LOOKUPS;\n if(turn.calls.some(c=>c.id!==call.id&&!lookups.has(c.function?.name)))return null;")
s=s.replace(" const data=decodeResult(last.content);if(!data)return null;", " const data=adapter?.decode?adapter.decode(last.content):decodeResult(last.content);if(!data)return null;")
s=s.replace("export function runProcedure(request,{timeoutMs=", "export function runProcedure(request,{timeoutMs=")
s=s.replace(" return new Promise(resolve=>{\n  const child=spawn", " const adapter=EXTENSIONS.get(request.tool||request.recipe?.tool);if(adapter)return Promise.resolve(adapter.run(request)).catch(()=>({ok:false,message:'Registered adapter failed.'}));\n return new Promise(resolve=>{\n  const child=spawn")
s=s.replace("export function formatProcedure(tool,data,query=''){\n", "export function formatProcedure(tool,data,query=''){\n const adapter=EXTENSIONS.get(tool);if(adapter)return adapter.format(tool,data,query);\n")
s=s.replace(" const saved=saveTemplate(candidate.query,proof.recipe", " if(proof.recipe.tool!==candidate.tool||!['read','write'].includes(proof.recipe.kind))return null;\n if(proof.recipe.kind==='write'&&currentTurn(body,userQuery)?.priorConstraints)return null;\n const saved=saveTemplate(candidate.query,proof.recipe")
s=s.replace(" const data=proof.recipe.kind==='write'?", " const data=proof.data??(proof.recipe.kind==='write'?")
s=s.replace("state:proof.recipe.desired}:candidate.data;", "state:proof.recipe.desired}:candidate.data);")
s+='''
// Only explicitly enabled, local adapter modules are loaded. Captured shell/code
// records do not become executable merely because a prior tool call completed.
try{
 const manifest=JSON.parse(readFileSync(ROOT+'/execution-adapters.json','utf8'));
 for(const entry of manifest.version===1&&Array.isArray(manifest.adapters)?manifest.adapters:[]){
  if(entry.enabled!==true||!/^[-a-zA-Z0-9_]+\\.mjs$/.test(entry.module||''))continue;
  const file=ROOT+'/lib/execution-adapters/'+entry.module;
  try{const mod=await import(file);registerExecutionAdapter(mod.default,file)}catch(error){console.log(JSON.stringify({event:'execution-adapter-disabled',module:entry.module,error:error?.name||'Error'}))}
 }
}catch{}
'''
p.write_text(s)
p=base/'execution-adapters.json';p.write_text(json.dumps({'version':1,'adapters':[{'module':'local-host-info.mjs','enabled':True}]},indent=2)+'\n')
p=base/'lib/execution-adapters/local-host-info.mjs';s=p.read_text().replace('remote|vm|virtual|gpu', 'remote|vm|virtual|docker|container|kubernetes|windows|macos|mac|android|ios|gpu');p.write_text(s)
p=base/'plugins/procedure-memory/index.js';(backup/'procedure-memory-plugin.js').write_text(p.read_text());s=p.read_text().replace("tasks.set(event.sessionID,{text:event.prompt?.text||'',workspace});", "tasks.set(event.sessionID,{text:event.prompt?.text||'',workspace,hasFiles:Boolean(event.prompt?.files?.length)});")
anchor="  await ctx.session.hook('context',async event=>{"
assert anchor in s
s=s.replace(anchor,"""  await ctx.session.hook('model.request',async event=>{
   const task=tasks.get(event.sessionID);if(!task||task.hasFiles)return;
   event.headers||={};
   if(event.headers['x-request-kind']==='ha'||event.headers['x-media-session'])return;
   const provider=event.model?.providerID;
   if(provider!=='openrouter'&&provider!=='evo-agent')return;
   event.baseURL='http://127.0.0.1:8011/'+(provider==='openrouter'?'generic-cloud':'generic-agent')+'/v1';
   event.headers['x-procedure-request-kind']=event.kind||'primary';
   event.headers['x-procedure-request-task']=encodeURIComponent(task.text);
  });
"""+anchor)
p.write_text(s)
print('Execution adapters registered globally; existing general procedure recall retained.')
