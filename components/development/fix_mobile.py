from pathlib import Path
import json,hashlib,shutil
h=Path.home();p=h/'.shellular/config.json';d=json.loads(p.read_text());old=d['machineId'];new=hashlib.sha256(Path('/etc/machine-id').read_text().strip().encode()).hexdigest();d['machineId']=new;p.write_text(json.dumps(d,indent=2));src=h/f'.shellular/shellular-{old}.e2ee';dst=h/f'.shellular/shellular-{new}.e2ee';shutil.copy2(src,dst)
p=h/'.config/opencode/plugins/opencode-mobile-v2/index.ts';t=p.read_text().replace('await v1Plugin(ctx)','await v1Plugin({ ...ctx, serverUrl: new URL("http://127.0.0.1:49374") })');p.write_text(t)
p=h/'.config/systemd/user/shellular.service';t=p.read_text().replace('StartLimitIntervalSec=0\n','');p.write_text(t)
print('Mobile listener and migrated host identity updated')
