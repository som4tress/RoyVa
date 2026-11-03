from pathlib import Path
p=Path.home()/'.config/opencode/telegram/bridge.mjs';s=p.read_text();lines=s.splitlines();header=lines.pop(0);assert lines[0].startswith('#!');lines.insert(1,header);p.write_text('\n'.join(lines)+'\n')
