import sys,pathlib
sys.path.insert(0,str(pathlib.Path.home()/'.config/opencode/mcp'))
from ha_status_report import collect
seen=[]
def read(path):
 seen.append(path);return [{'entity_id':'light.x','state':'on','attributes':{'friendly_name':'Example light'}},{'entity_id':'switch.y','state':'off','attributes':{'friendly_name':'Example switch'}},{'entity_id':'sensor.z','state':'42','attributes':{'friendly_name':'Diagnostic'}}]
r=collect({},read);assert r['total']==2 and seen==['/api/states'] and r['read_only']
assert collect({'domains':['light'],'state':'off'},read)['total']==0
assert collect({'name':'switch','limit':1},read)['rows']==[['Example switch','switch','off']]
assert collect({'limit':1},read)['truncated']
assert collect({'domains':['sensor']},read)['total']==1
for args in [{'domains':['invalid']},{'limit':0},{'limit':201},{'limit':True},{'url':'bad'}]:
 try:collect(args,read);raise AssertionError('invalid input accepted')
 except ValueError:pass
print('PASS: fixed read-only endpoint, scope/filtering, sensor opt-in, row bounds and invalid input rejection.')
