from pathlib import Path
h=Path.home();base=h/'.config/opencode';backup=h/'opencode-migration-backup/review-fixes';backup.mkdir(exist_ok=True)
for rel in ['plugins/ha-mcp-routing/index.js','plugins/ha-mcp-routing/phrases.js','scripts/openrouter-usage','telegram/bridge.mjs','instructions/usage-footer.md']:
 p=base/rel;(backup/rel.replace('/','__')).write_text(p.read_text())
p=base/'plugins/ha-mcp-routing/phrases.js';s=p.read_text();s+='''
/** Tool identity, not the server namespace, determines historical semantics. */
export function phraseKindForTool(tool,result={}){
 if(result?.isError||result?.error)return null;
 for(const text of [result?.output,...(Array.isArray(result?.content)?result.content:[]).map(c=>c.text)].filter(t=>typeof t==='string')){
  try{const d=JSON.parse(text);if(d.error||d.isError||d.logbook_error||d.data?.failed?.length)return null}catch{}
 }
 if(tool==='ha-history_get_visited_locations')return 'history';
 if(/^ha[-_]history_(?:get_device_status|get_device_status_report|get_on_entities_with_context)$/.test(tool)||/^home[-_]assistant_/.test(tool))return 'devices';
 return null;
}
''';p.write_text(s)
p=base/'plugins/ha-mcp-routing/index.js';s=p.read_text().replace("import {findPhrase,rememberPhrase}","import {findPhrase,rememberPhrase,phraseKindForTool}")
s=s.replace("const phraseKind=/^ha[-_]history_/.test(event.tool)?'history':'devices';", "const phraseKind=phraseKindForTool(event.tool,event.result||{});")
s=s.replace('if(text&&rememberPhrase(phrasePath,text,phraseKind))','if(text&&phraseKind&&rememberPhrase(phrasePath,text,phraseKind))');p.write_text(s)
# Existing learned categories lack provenance: quarantine rather than trust them.
p=h/'.local/share/opencode/ha-router/learned-phrases.json'
if p.exists():(backup/'learned-phrases.json').write_bytes(p.read_bytes());p.write_text('{"version":1,"phrases":[]}\n');p.chmod(0o600)
p=h/'.config/systemd/user/opencode-telegram.service';(backup/'opencode-telegram.service').write_text(p.read_text());s=p.read_text().replace('Environment=OPENCODE_TG_MODEL=openrouter/deepseek/deepseek-v4.1-flash-1017','Environment=OPENCODE_TG_MODEL=opencode/glm-5.3-flash-free');p.write_text(s)
p=base/'telegram/bridge.mjs';s=p.read_text().replace('const texts = [];','const texts = [];\n    const usageIds=new Set();\n    const invocationStarted=Date.now();')
s=s.replace('        const part = ev.part;', '        const part = ev.part;\n        if(part?.messageID)usageIds.add(part.messageID);')
s=s.replace('    child.on("close", (code) => {','    child.on("close", async (code) => {')
s=s.replace('if (text && !aborted && !errorText) return resolve({ ok: true, text, references });', '''if (text && !aborted && !errorText) {
        let footer='';
        if(usageIds.size)footer=await new Promise(done=>{
          const usage=spawn('/usr/bin/python3',[homedir()+'/.config/opencode/scripts/openrouter-usage','--session',sessionId,'--message-ids',[...usageIds].join(','),'--until-ms',String(Date.now())],{stdio:['ignore','pipe','ignore'],env:process.env});
          let out='';const limit=setTimeout(()=>{usage.kill('SIGKILL');done('')},2000);
          usage.stdout.on('data',data=>out+=data.toString());usage.on('error',()=>{clearTimeout(limit);done('')});usage.on('close',status=>{clearTimeout(limit);done(status===0?out.trim():'')});
        });
        const clean=text.replace(/\\nUsage(?: \\(local\\))?: \\$[^\\n]*$/,'').trim();
        return resolve({ok:true,text:footer?clean+'\\n\\n'+footer:clean,references});
      }''')
p.write_text(s)
p=base/'instructions/usage-footer.md';p.write_text('''# Usage reporting
Telegram appends a usage footer in code after a completed invocation, using only that invocation's assistant message IDs and linked subagent messages. Do not run a usage script or manufacture a footer while generating a normal reply: that adds another model call and cannot include its own final cost. Local, free-provider and zero-inference turns have no paid OpenRouter footer. Other OpenCode frontends retain their native usage display; do not invent per-request figures.
For an explicit usage query, use scripts/openrouter-usage with --session and either --message-ids or a bounded --since-ms/--until-ms window. It is stateless and does not consume a shared cursor. Account-wide credit balances are not per-turn usage and are excluded from the footer.
''')
print('Tool-specific phrase learning installed; old ambiguous phrase records backed up. Telegram now selects the configured free model; footer runs after completion.')
