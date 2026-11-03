import importlib.util,pathlib,json,subprocess,time,os
r=pathlib.Path(__file__).parent
# Reuse the exact completed batch benchmark's replay and measurement function,
# without executing its orchestration loop.
source=(r.parent/'batch-benchmark-20261103/bench.py').read_text().split('\ntry:\n for n in ')[0]
ns={'__file__':str(r.parent/'batch-benchmark-20261103/bench.py')};exec(source,ns)
ns['r']=r
config=r.parent/'servers.json';env=ns['env'];restored=False
baseline=json.loads((r.parent/'batch-benchmark-20261103/results.json').read_text())[0]
(r/'baseline.json').write_text(json.dumps(baseline,indent=2))
def setting(eager):
 d=json.loads(config.read_text());d['servers']['agent']['enforce_eager']=eager;d['servers']['agent']['batch_tokens']=2048;config.write_text(json.dumps(d,indent=2)+'\n')
def restart():
 subprocess.run(['systemctl','--user','reset-failed','evo-vllm-agent'],env=env,capture_output=True)
 p=subprocess.run(['systemctl','--user','restart','evo-vllm-agent'],env=env,capture_output=True,text=True,timeout=650)
 if p.returncode:raise RuntimeError('Agent failed startup')
try:
 setting(False);print(json.dumps({'event':'starting-optimized','batch':2048,'concurrency':2}),flush=True);restart()
 print(json.dumps({'event':'optimized-ready'}),flush=True)
 result=ns['measure'](2048);(r/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps({'event':'result',**result}),flush=True)
 # Compare generation rates rather than variable output lengths.
 def rate(x):return (x['usage']['completion_tokens']-1)/(x['total_s']-x['ttft_s'])
 gain=rate(result)/rate(baseline)-1
 keep=result['valid_tool_json'] and result['finish_reason']!='length' and gain>=.1 and result['ttft_s']<=baseline['ttft_s']*1.2
 decision={'keep_optimized':keep,'generation_gain_pct':gain*100,'baseline':baseline,'optimized':result,'note':'One matched cold replay; output text and length can vary. Baseline from prior same-payload benchmark.'}
 (r/'decision.json').write_text(json.dumps(decision,indent=2))
 if not keep:setting(True);print(json.dumps({'event':'restoring-eager'}),flush=True);restart();restored=True
 print(json.dumps({'event':'finished','keep_optimized':keep,'generation_gain_pct':gain*100}),flush=True)
except Exception as e:
 (r/'failure.json').write_text(json.dumps({'error':type(e).__name__,'message':str(e)},indent=2))
 print(json.dumps({'event':'failed','error':type(e).__name__,'restoring_eager':True}),flush=True)
 setting(True);restart();print(json.dumps({'event':'restored-eager'}),flush=True)
