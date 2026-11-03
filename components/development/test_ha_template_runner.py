import sys,pathlib,copy,datetime as dt
sys.path.insert(0,str(pathlib.Path.home()/'.config/opencode/mcp'))
import ha_template_runner as r
row={'entity_id':'light.hall_lamp','state':'off','attributes':{'friendly_name':'Hall Lamp'}};calls=[]
r.read_api=lambda path:[copy.deepcopy(row)]
def mcp(tool,args):calls.append((tool,args));row['state']='on' if tool==r.ON else 'off';return {}
r.mcp_call=mcp
query='Turn Hall Lamp on';args={'name':'Hall Lamp','domain':['light']}
row['state']='on';proof=r.certify({'tool':r.ON,'args':args,'query':query,'data':{'data':{'success':[{'id':row['entity_id']}],'failed':[]}}})
recipe=proof['recipe'];assert recipe['expected_entities']==['light.hall_lamp'];row['state']='off'
result=r.execute({'query':query,'recipe':recipe});assert result['ok'] and row['state']=='on' and len(calls)==1
result=r.execute({'query':query,'recipe':recipe});assert result['ok'] and result['data']['already'] and len(calls)==1
for q,a in [('Turn all lights on',args),('Do not turn Hall Lamp on',args),('Turn Hall Lamp on if I get home',args),('Turn Hall Lamp on for 10 minutes',args),('Turn Hall Lamp off',args),('Turn it on',args),('Turn Hall Lamp on',{'name':'Hall Lamp','area':'Hall'})]:
 try:r.checked_args(r.ON,a,q);raise AssertionError('unsafe write accepted')
 except ValueError:pass
row['attributes']['friendly_name']='Server PC';row['entity_id']='switch.server_pc'
try:r.target_for({'name':'Server PC','domain':['switch']});raise AssertionError('server allowed')
except ValueError:pass
row.update(entity_id='light.hall_lamp',state='off',attributes={'friendly_name':'Hall Lamp'})
r.mcp_call=lambda *a:(_ for _ in ()).throw(RuntimeError('network'))
assert r.execute({'query':query,'recipe':recipe})['write_uncertain']
assert 'date' not in r.checked_args(r.HISTORY,{'person':'somdutta','date':'2000-01-01'},'Which recorded locations did Somdutta visit today?')
y=r.checked_args(r.HISTORY,{'person':'somdutta'},'Which recorded locations did Somdutta visit yesterday?');assert y['date']==(dt.datetime.now(r.TZ).date()-dt.timedelta(days=1)).isoformat()
for q in ['What is Hall Lamp brightness?','How long was Hall Lamp on?']:
 try:r.checked_args(r.STATUS,{'name':'Hall Lamp'},q);raise AssertionError('analytical query accepted')
 except ValueError:pass
print('PASS: actual-target certification, fresh reads, single scoped writes, already-state skip, conditional/negation/broad/scheduled rejection, computer exclusion, uncertain-write no-retry, fresh relative dates and analytical fallback.')
