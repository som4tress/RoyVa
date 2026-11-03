import sys,pathlib,json,io,datetime as dt
sys.path.insert(0,str(pathlib.Path.home()/'.config/opencode/mcp'))
import ha_history as h
h.connection=lambda:({'url':'https://ha.example/api/mcp'},'Bearer fixture')
now=dt.datetime.now(h.TZ);seen=[]
class Response(io.StringIO):
 def __enter__(self):return self
 def __exit__(self,*a):self.close()
def fake(req,timeout):
 seen.append(req.full_url)
 rows=[{'entity_id':'person.shobha','state':'home','last_changed':(now-dt.timedelta(hours=2)).isoformat()},{'entity_id':'person.shobha','state':'Park','last_changed':(now-dt.timedelta(minutes=20)).isoformat()},{'entity_id':'person.shobha','state':'not_home','last_changed':(now-dt.timedelta(minutes=5)).isoformat()}]
 return Response(json.dumps([rows]))
h.urllib.request.urlopen=fake
result=h.get_history({'person':'shobha','hours':1});r=result['requested_range'];start=dt.datetime.fromisoformat(r['from']);end=dt.datetime.fromisoformat(r['to'])
assert abs((end-start).total_seconds()-3600)<2;assert len(result['recorded_locations'])==2;assert result['transit_or_unknown_intervals'];assert all(dt.datetime.fromisoformat(x['from'])>=start for x in result['recorded_locations'])
for args in [{'person':'shobha','hours':0},{'person':'shobha','hours':True},{'person':'shobha','hours':1,'date':'2026-10-30'}]:
 try:h.get_history(args);raise AssertionError('invalid window accepted')
 except ValueError:pass
print('PASS: rolling one-hour recorder window, multiple historical locations, transit gaps, clipping and invalid-input rejection.')
