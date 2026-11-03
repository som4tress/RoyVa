from pathlib import Path
import json,shutil
h=Path.home();p=h/'.shellular/config.json';d=json.loads(p.read_text());files=list((h/'.shellular').glob('shellular-*.e2ee'));old='0a20d22f701cbf34cc3f3218bca1f3fa2b6931eaa7cbd7c36145fb7445f047c0';d['machineId']=old;p.write_text(json.dumps(d,indent=2))
p=h/'OpenCode/shellular/packages/cli/dist/main.js';t=p.read_text().replace('Rn=No.machineIdSync()','Rn=process.env.SHELLULAR_MIGRATED_MACHINE_ID||No.machineIdSync()');p.write_text(t)
p=h/'.config/systemd/user/shellular.service';t=p.read_text().replace('[Service]','[Service]\nEnvironment=SHELLULAR_MIGRATED_MACHINE_ID='+old);p.write_text(t)
