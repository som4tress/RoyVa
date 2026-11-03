from pathlib import Path
p=Path.home()/'.config/opencode/lib/free-quota.mjs';s=p.read_text().replace("export const FREE_QUOTA=homedir()+'/.local/state/opencode/free-model-quota.json';", "export const FREE_QUOTA=process.env.OPENCODE_FREE_QUOTA_FILE||homedir()+'/.local/state/opencode/free-model-quota.json';");p.write_text(s)
