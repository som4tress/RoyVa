from pathlib import Path
p=Path('/tmp/test_generic_templates_live.py');s=p.read_text().replace('for index in [1,2]:','for index in [1]:')
Path('/tmp/test_crossmodel_template.py').write_text(s.replace('openrouter/deepseek/deepseek-v4.1-flash-1017','evo-agent/qwen36-agent').replace('template-host-','template-crossmodel-'))
Path('/tmp/test_generic_fallback.py').write_text(s.replace("What is this computer's kernel version? Use uname -r.",'Without using tools, reply exactly: fallback working').replace('template-host-','template-fallback-'))
