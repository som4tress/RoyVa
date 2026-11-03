from pathlib import Path
p=Path('/tmp/test_scoped_usage.py');s=p.read_text().replace("part={'tool':'subagent'","part={'type':'tool','tool':'subagent'");p.write_text(s)
