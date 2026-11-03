import sys,os,json,urllib.parse
from pathlib import Path
sys.path.insert(0,'/home/somdutta/.config/opencode/mcp')
for name in ['api.env','opencode.env','ha.env']:
 for line in (Path('/home/somdutta/llm-server')/name).read_text().splitlines():
  if '=' in line:
   k,v=line.split('=',1);os.environ[k]=v.strip('"\'')
import ha_history
p='/api/history/period/2026-10-31T07:00:00+00:00?'+urllib.parse.urlencode({'filter_entity_id':'sensor.front_doorbell_last_activity','end_time':'2026-11-01T07:00:00+00:00','significant_changes_only':'0'})
d=ha_history.read_api(p);rows=d[0] if d else [];path=Path('/home/somdutta/llm-server/audit15-20261103/ring-history.json');path.write_text(json.dumps(rows));path.chmod(0o600);print({'rows':len(rows),'attributeKeys':list(rows[0].get('attributes',{})) if rows else []})
