"""Direct Qwen comparison: two read-only tasks, official sampling, real tools.

Public web tools use a file broker so the caller can supply actual search/fetch
results. Private HA tools execute locally. Nothing changes the serving engine.
"""
import datetime as dt
import json,os,re,sys,time,urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
HOME=Path.home()
TZ=ZoneInfo('America/Los_Angeles')
for name in ('api.env','ha.env'):
    for line in (HOME/'llm-server'/name).read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1);os.environ[k.strip()]=v.strip().strip('"\'')
sys.path.insert(0,str(HOME/'.config/opencode/mcp'))
import ha_history,ha_device_status

TOOLS=json.loads((ROOT/'web-tools.schema.json').read_text())
for module in (ha_device_status,ha_history):
    t=module.TOOL
    TOOLS.append({'type':'function','function':{'name':t['name'],'description':t['description'],'parameters':t['inputSchema']}})
PROFILES={
    'nonthinking':{'temperature':.7,'top_p':.8,'top_k':20,'min_p':0.,'presence_penalty':1.5,'repetition_penalty':1.},
    'thinking':{'temperature':1.,'top_p':.95,'top_k':20,'min_p':0.,'presence_penalty':1.5,'repetition_penalty':1.},
}

def save(path,value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,indent=2));temporary.chmod(0o600);temporary.replace(path)

def cache_metrics():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8000/metrics',timeout=5) as response:text=response.read().decode()
        return {kind:sum(float(line.rsplit(' ',1)[1]) for line in text.splitlines()
            if line.startswith('vllm:prefix_cache_'+kind+'_total')) for kind in ('hits','queries')}
    except Exception:return None

def model(messages,mode):
    body={'model':'qwen36-agent','messages':messages,'tools':TOOLS,'stream':False,
          'max_tokens':32768,'include_reasoning':True,
          'chat_template_kwargs':{'enable_thinking':mode=='thinking'},**PROFILES[mode]}
    # No salt, cache toggle, gateway, compaction or application-result cache.
    request=urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',data=json.dumps(body).encode(),
        headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ['VLLM_API_KEY']})
    start=time.monotonic()
    with urllib.request.urlopen(request,timeout=240) as response:data=json.load(response)
    return data,round(time.monotonic()-start,3)

def tool(name,args,case,step):
    if name=='get_device_status':return ha_device_status.collect(args,ha_history.read_api)
    if name=='get_visited_locations':return ha_history.get_history(args)
    if name not in ('websearch','webfetch'):return {'error':'Tool is unavailable in this read-only comparison.'}
    ident=case+'-'+str(step)+'-'+str(time.time_ns())
    output=ROOT/(ident+'.web-result.json')
    save(ROOT/'pending.json',{'id':ident,'case':case,'name':name,'args':args,'resultFile':str(output)})
    print(json.dumps({'event':'web-needed','case':case,'id':ident,'tool':name}),flush=True)
    start=time.monotonic()
    while not output.exists():
        if time.monotonic()-start>180:raise TimeoutError('Web tool response not supplied')
        time.sleep(.2)
    result=json.loads(output.read_text())
    (ROOT/'pending.json').unlink(missing_ok=True)
    return result

def run(task,mode):
    case=task+'-'+mode;now=dt.datetime.now(TZ)
    prompt=(f'As of {now.isoformat(timespec="seconds")}, what does the weather look like through 21 November in Milpitas, California?'
        if task=='weather' else f'Where is Shobha likely to be at {now.isoformat(timespec="seconds")}? Give the best estimate from the available location evidence and distinguish observations from uncertainty.')
    messages=[{'role':'system','content':f'You are a helpful assistant. Current local date and time: {now.isoformat()}. Timezone: America/Los_Angeles. Answer concisely using the available tools when needed.'},
              {'role':'user','content':prompt}]
    record={'case':case,'task':task,'mode':mode,'prompt':prompt,'profile':PROFILES[mode],
        'steps':[],'complete':False,'cacheBefore':cache_metrics()}
    started=time.monotonic();print(json.dumps({'event':'start','case':case,'at':now.isoformat()}),flush=True)
    try:
        for step in range(1,7):
            data,seconds=model(messages,mode)
            choice=data['choices'][0];message=choice['message']
            entry={'pass':step,'llmSeconds':seconds,'usage':data.get('usage'),
                'finish':choice.get('finish_reason'),'tools':[],'reasoningChars':len(message.get('reasoning') or message.get('reasoning_content') or '')}
            record['steps'].append(entry)
            # Preserve the provider's actual message, including reasoning fields.
            messages.append(message)
            if message.get('tool_calls'):
                for call in message['tool_calls']:
                    name=call['function']['name'];args=json.loads(call['function']['arguments']);stamp=time.monotonic()
                    result=tool(name,args,case,step)
                    waited=round(time.monotonic()-stamp,3)
                    seconds=result.pop('_benchmarkSeconds',waited) if isinstance(result,dict) else waited
                    if isinstance(result,dict) and '_brokerContent' in result:result=result['_brokerContent']
                    entry['tools'].append({'name':name,'args':args,'seconds':seconds,'brokerWaitSeconds':waited,'result':result})
                    messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result)})
            else:
                record['answer']=message.get('content');record['complete']=choice.get('finish_reason')=='stop' and bool(record['answer']);break
            save(ROOT/(case+'.result.json'),record)
        else:record['error']='Six-pass diagnostic limit reached; not a completed answer.'
    except Exception as exc:record['error']=type(exc).__name__+': '+str(exc)[:160]
    record['seconds']=round(time.monotonic()-started,3);record['cacheAfter']=cache_metrics()
    record['modelSeconds']=round(sum(s['llmSeconds'] for s in record['steps']),3)
    record['toolSeconds']=round(sum(t['seconds'] for s in record['steps'] for t in s['tools']),3)
    record['executionSeconds']=round(record['modelSeconds']+record['toolSeconds'],3)
    record['inputTokens']=sum((s.get('usage') or {}).get('prompt_tokens',0) for s in record['steps'])
    record['outputTokens']=sum((s.get('usage') or {}).get('completion_tokens',0) for s in record['steps'])
    save(ROOT/(case+'.result.json'),record)
    print(json.dumps({k:record.get(k) for k in ('case','complete','seconds','modelSeconds','executionSeconds','inputTokens','outputTokens','error')}),flush=True)
    return record

if __name__=='__main__':
    results=[]
    for task,mode in [('weather','nonthinking'),('location','thinking'),('weather','thinking'),('location','nonthinking')]:
        results.append(run(task,mode));save(ROOT/'results.json',results)
