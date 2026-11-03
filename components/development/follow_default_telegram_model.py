from pathlib import Path
import re
h=Path.home();p=h/'.config/opencode/telegram/bridge.mjs';s=p.read_text();old='const MODEL = process.env.OPENCODE_TG_MODEL || "openrouter/deepseek/deepseek-v4.1-flash-1017";'
new='''function getModel() {
  if(process.env.OPENCODE_TG_MODEL)return process.env.OPENCODE_TG_MODEL;
  try{return JSON.parse(readFileSync(join(homedir(),'.config/opencode/opencode.json'),'utf8')).model||'opencode/glm-5.3-flash-free'}catch{return 'opencode/glm-5.3-flash-free'}
}'''
assert old in s;s=s.replace(old,new);s=re.sub(r'\bMODEL\b','getModel()',s);s=s.replace('    const invocationStarted=Date.now();\n','');p.write_text(s)
p=h/'.config/systemd/user/opencode-telegram.service';s=p.read_text();s='\n'.join(l for l in s.split('\n') if not l.startswith('Environment=OPENCODE_TG_MODEL='));p.write_text(s)
p=Path('/tmp/test_bridge_review_live.mjs');s=p.read_text().replace("process.env.OPENCODE_TG_MODEL=unit.match(/^Environment=OPENCODE_TG_MODEL=(.+)$/m)[1];", "process.env.OPENCODE_TG_MODEL=JSON.parse(readFileSync(home+'/.config/opencode/opencode.json','utf8')).model;")
p.write_text(s)
