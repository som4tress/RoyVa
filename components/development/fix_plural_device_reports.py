from pathlib import Path
p=Path.home()/'.config/opencode/lib/ha-reports.mjs';s=p.read_text();s=s.replace("/\\b(table|tabular|inventory|report)\\b/.test(s)||", "/\\b(table|tabular|inventory|report)\\b/.test(s)||/\\b(lights|devices|switches|fans|entities|sensors)\\b/.test(s)||")
s=s.replace('past|when|explain)', 'past|last|ago|earlier|when|explain)');p.write_text(s)
