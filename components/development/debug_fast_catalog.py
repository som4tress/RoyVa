from pathlib import Path
p=Path.home()/'.config/opencode/plugins/ha-mcp-routing/index.js';s=p.read_text().replace("   if(state.fastStatus)for", "   if(state.fastStatus)log({sessionID:event.sessionID,event:'fast-tool-catalog',tools:Object.keys(event.tools)});\n   if(state.fastStatus)for");p.write_text(s)
