from pathlib import Path
h=Path.home();p=h/'.config/opencode/plugins/ha-mcp-routing/index.js';s=p.read_text().replace("const presence=s=>PEOPLE.test(s)&&", "const presence=s=>PEOPLE.test(s)&&!/\\b(turn|switch|set|dim|lights?|fans?|thermostat)\\b/.test(s)&&");p.write_text(s)
