import sys,types,importlib.util
from pathlib import Path
p=Path.home()/'.config/opencode/mcp/ha_status_report.py';spec=importlib.util.spec_from_file_location('report',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
registry={'areas':{'a':{'name':'Sample Room','floor_id':'f'}},'floors':{'f':{'name':'Sample Floor'}},'devices':{'d':{'area_id':'a'}},'entities':{'light.one':{'device_id':'d'},'switch.config':{'device_id':'d','entity_category':'config'},'switch.diagnostic':{'device_id':'d','entity_category':'diagnostic'},'fan.off':{'device_id':'d'},'light.unavailable':{'device_id':'d'}}}
sys.modules['ha_registry']=types.SimpleNamespace(snapshot=lambda:registry)
states=[{'entity_id':e,'state':s,'attributes':{'friendly_name':e}} for e,s in [('light.one','on'),('switch.config','on'),('switch.diagnostic','on'),('fan.off','off'),('light.unavailable','unavailable')]]
read=lambda path:states
r=m.collect({'floor':'Sample Floor','states':['on','unavailable']},read);assert len(r['rows'])==2;assert {x[2] for x in r['rows']}=={'on','unavailable'};assert all('config' not in x[0] and 'diagnostic' not in x[0] for x in r['rows'])
assert len(m.collect({},read)['rows'])==3
assert len(m.collect({'include_diagnostics':True},read)['rows'])==5
try:m.collect({'state':'on','states':['off']},read);raise AssertionError('Conflicting filters accepted')
except ValueError:pass
assert 'states' in m.TOOL['inputSchema']['properties'];print('PASS: authoritative category exclusion, OR states, unscoped defaults, opt-in diagnostics, conflict rejection')
