from pathlib import Path
h=Path.home();base=h/'.config/opencode';backup=h/'opencode-migration-backup/execution-templates';backup.mkdir(exist_ok=True)
p=base/'lib/media-deadline-proxy.mjs';(backup/p.name).write_text(p.read_text());s=p.read_text();s="import {tryExecutionTemplate,learnExecutionTemplate} from './execution-templates.mjs';\n"+s
needle="  const report=ha&&!cloud?reportFromRequest(incoming):null;"
assert needle in s
s=s.replace(needle,"""  if(ha&&!cloud){
   let direct=null;
   try{direct=await tryExecutionTemplate(incoming);if(!direct)direct=await learnExecutionTemplate(incoming)}catch(error){console.log(JSON.stringify({at:new Date().toISOString(),route:'template-fallback',error:error?.name||'Error'}))}
   if(direct){
    const wire=reportWire(incoming,direct.text);
    res.writeHead(200,{'content-type':wire.type});res.end(wire.body);
    console.log(JSON.stringify({at:new Date().toISOString(),route:direct.source,status:200,zeroLLM:direct.zeroLLM,session:req.headers['x-media-session'],chars:direct.text.length}));return;
   }
  }
  const report=ha&&!cloud?reportFromRequest(incoming):null;""")
p.write_text(s)
p=h/'.config/systemd/user/opencode-media-deadline.service';(backup/p.name).write_text(p.read_text());s=p.read_text()
if 'llm-server/ha.env' not in s:s=s.replace('[Service]','[Service]\nEnvironmentFile=/home/somdutta/llm-server/ha.env')
p.write_text(s)
p=base/'instructions/routing.md';p.write_text(p.read_text()+'\nVerified execution templates (2026-10-31): the shared HA model gateway can execute certified exact-repeat requests without LLM inference. Supported procedures are bounded status reads, device tables, single-person/day location history, and uniquely targeted light/switch/fan on-off intents. New wording uses the ordinary agent; a successful compatible MCP result is revalidated and formatted in code, then its procedure is saved automatically. Context-dependent, analytical, conflicting or changed procedures fall back. Code/config fingerprints and 30-day validity limit stale templates. Every replay fetches live data; relative dates are resolved fresh. Writes require an explicit current standalone command, unique target, protected-computer checks and state verification; uncertain writes are never automatically retried. Stores: ~/.local/share/opencode/procedures/templates.json and execution.jsonl. General code/shell procedures remain advisory recall, not automatic execution.\n')
print('Shared execution path enabled, with audit and automatic promotion of compatible verified MCP results.')
