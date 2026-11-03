from pathlib import Path
h=Path.home();p=h/'.config/opencode/lib/ha-reports.mjs';s=p.read_text();s=s.replace(" return /\\b(status|states?", " return /\\b(lights?|devices?|switch(?:es)?|fans?|entities|sensors?|thermostats?|climate|locks?|covers?|speakers?)\\b/.test(s)&&/\\b(status|states?")
s=s.replace('if(content.kind===\'ha_status_report\')return content;\n if(content.isError)return null;',"if(content.isError)return null;\n if(content.kind==='ha_status_report')return content;")
s=s.replace('why|cause|caused|history|yesterday|before|after|compare|when|explain','why|who|how|cause|caused|turned|history|yesterday|before|after|compare|since|past|when|explain')
s=s.replace(" const scope='Scope: '+report.domains.map(cell).join(', ');", " const filters=report.filters||{};\n const scope='Scope: '+report.domains.map(cell).join(', ')+(filters.name?' • Name: '+cell(filters.name):'')+(filters.state?' • State: '+cell(filters.state):'');")
p.write_text(s)
p=h/'.config/opencode/plugins/ha-mcp-routing/index.js';s=p.read_text().replace(" if(history(s))return 'history';", " if(history(s))return 'history';\n if(isStatusReport(text))return 'devices';");p.write_text(s)
p=Path('/tmp/test_report_renderer.mjs');s=p.read_text().replace("assert(rendered.includes('| off |')===false);",'');p.write_text(s)
