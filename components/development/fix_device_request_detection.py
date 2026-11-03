from pathlib import Path
h=Path.home();p=h/'.config/opencode/plugins/ha-mcp-routing/index.js';s=p.read_text().replace('blind\\w*|den switch)','blind\\w*|switches?|devices?|entities|lamps?|den switch)')
p.write_text(s)
p=h/'.config/opencode/mcp/ha_history.py';s=p.read_text().replace('on a local calendar date. Use for','on a local calendar date or rolling last N hours. Pass hours=N for rolling windows; do not combine hours with date. Use for');p.write_text(s)
p=h/'.config/opencode/lib/execution-templates.mjs';s=p.read_text().replace("if(!data.recorded_locations.length)return title+", "if(!data.recorded_locations.length&&!(range?.hours&&data.transit_or_unknown_intervals?.length))return title+")
p.write_text(s)
