from pathlib import Path
h=Path.home();p=h/'.config/opencode/lib/procedure-memory.mjs';s=p.read_text().replace("import {dirname,resolve} from 'node:path';","import {dirname,resolve,basename} from 'node:path';")
s=s.replace("&&e.tokens?.filter(t=>ACTION.has(t)).join('|')===pol", "&&(e.files.some(f=>task.includes(f.path)||task.includes(basename(f.path)))||e.tokens?.filter(t=>ACTION.has(t)).join('|')===pol)")
s=s.replace("return {entry:e,score:common/union.size};", "const artifact=e.files.some(f=>task.includes(f.path)||task.includes(basename(f.path)));\n  return {entry:e,score:artifact?1:common/union.size};")
s=s.replace('Reuse an existing tool/file where relevant after inspecting it;', 'Inspect and reuse an existing tool/file where relevant; a prior write is not a reason to rewrite an unchanged file;')
p.write_text(s)
