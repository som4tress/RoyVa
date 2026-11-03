from pathlib import Path
s=(Path.home()/'OpenCode/shellular/packages/cli/dist/main.js').read_text()
for needle in ['Rn=','machineIdSync','machine-id']:
 i=s.find(needle);print(needle,s[max(0,i-150):i+300])
