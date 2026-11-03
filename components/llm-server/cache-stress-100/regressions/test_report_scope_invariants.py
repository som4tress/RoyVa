import sys,types,pathlib
sys.path.insert(0,str(pathlib.Path.home()/'.config/opencode/mcp'))
from ha_status_report import collect
reg={'areas':{'a':{'name':'Office','floor_id':'f'},'b':{'name':'Ground','floor_id':'u'},'c':{'name':'Hall','floor_id':'f'}},'floors':{'f':{'name':'Ground'},'u':{'name':'Upper'}},'devices':{'d1':{'area_id':'a'},'d2':{'area_id':'b'}},'entities':{'light.inherited':{'device_id':'d1'},'light.override_excluded':{'device_id':'d1','area_id':'b'},'light.override_included':{'device_id':'d2','area_id':'c'}}}
sys.modules['ha_registry']=types.SimpleNamespace(snapshot=lambda:reg)
rows=[{'entity_id':eid,'attributes':{'friendly_name':eid},'state':'on'}for eid in reg['entities']]
r=collect({'floor':'Ground','domains':['light']},lambda _:rows);assert {x[0]for x in r['rows']}=={'light.inherited','light.override_included'};assert r['columns']==['Device','Type','State','Area']
r=collect({'area':'Ground','domains':['light']},lambda _:rows);assert [x[0]for x in r['rows']]==['light.override_excluded']
for bad in [{'floor':'Unknown'},{'area':''},{'floor':123}]:
 try:collect(bad,lambda _:rows)
 except ValueError:pass
 else:raise AssertionError('Invalid scope accepted')
r=collect({'name':'light.override_excluded','domains':['light']},lambda _:rows);assert len(r['rows'])==1 and r['columns']==['Device','Type','State']
reg['areas']['duplicate']={'name':'Office','floor_id':'u'}
try:collect({'area':'Office'},lambda _:rows)
except ValueError:pass
else:raise AssertionError('Ambiguous scope accepted')
print('PASS: entity area overrides device inheritance; floor and identically named area stay distinct; unknown/ambiguous/invalid scopes rejected; unscoped name behavior preserved. Fixture only.')
