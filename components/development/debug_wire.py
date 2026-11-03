from pathlib import Path
p=Path.home()/'.config/opencode/plugins/ha-mcp-routing/index.js';s=p.read_text().replace("    body.tools=(body.tools||[]).filter", "    log({sessionID:event.sessionID,event:'fast-wire-tools',tools:(body.tools||[]).map(t=>({type:t.type,name:t.function?.name||t.name,keys:Object.keys(t)}))});\n    body.tools=(body.tools||[]).filter");p.write_text(s)
