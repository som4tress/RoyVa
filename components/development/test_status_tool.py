import sys,pathlib
sys.path.insert(0,str(pathlib.Path.home()/'.config/opencode/mcp'))
from ha_device_status import collect
calls=[]
def read(path):
 calls.append(path);return [{'entity_id':'switch.shivi_light','state':'on','attributes':{'friendly_name':'Shivi Bedroom Light','secret':'not returned'}},{'entity_id':'light.fan','state':'off','attributes':{'friendly_name':'Shivi Room Fan'}}]
r=collect({'name':'Shivi Bedroom Light','domain':['switch']},read);assert r['count']==1 and r['matches'][0]['state']=='on';assert 'secret' not in str(r);assert calls==['/api/states'];assert collect({'name':'Missing'},read)['count']==0
for args in [{'name':''},{'name':'Shivi','url':'bad'},{'name':'Shivi','domain':['invalid']}]:
 try:collect(args,read);raise AssertionError('accepted bad input')
 except ValueError:pass
try:collect({'name':'Shivi'},lambda _:read('x')*11);raise AssertionError('unbounded output')
except ValueError:pass
p=pathlib.Path('/tmp/ha_speed_test.mjs');p.write_text(p.read_text().replace('home-assistant_homeassistant__GetLiveContext','ha-history_get_device_status'))
print('PASS: fixed read-only endpoint, name/domain filtering, no unrelated attributes, bounded results and invalid-input rejection.')
