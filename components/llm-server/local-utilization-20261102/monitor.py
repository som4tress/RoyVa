from pathlib import Path
import json,time,subprocess,sys,re,urllib.request
root=Path(__file__).parent;phase=sys.argv[1];env={}
for l in (Path.home()/'llm-server/api.env').read_text().splitlines():
 if '=' in l:k,v=l.split('=',1);env[k]=v.strip('"\'')
names={'vllm:prompt_tokens_total','vllm:generation_tokens_total','vllm:num_requests_running','vllm:num_requests_waiting','vllm:prefix_cache_hits_total','vllm:prefix_cache_queries_total','vllm:request_prefill_time_seconds_sum','vllm:request_prefill_time_seconds_count','vllm:request_decode_time_seconds_sum','vllm:request_decode_time_seconds_count','vllm:time_to_first_token_seconds_sum','vllm:time_to_first_token_seconds_count','vllm:num_preemptions_total'}
def metrics():
 try:
  q=urllib.request.Request('http://127.0.0.1:8000/metrics',headers={'Authorization':'Bearer '+env['VLLM_API_KEY']});text=urllib.request.urlopen(q,timeout=2).read().decode();out={}
  for line in text.splitlines():
   if not line or line.startswith('#'):continue
   name=line.split('{')[0].split(' ')[0]
   if name in names:out[name]=out.get(name,0)+float(line.split()[-1])
  return out
 except Exception:return {}
def integer(p):
 try:return int(Path(p).read_text())
 except:return None
samples=[];before=metrics();p=subprocess.Popen(['/home/somdutta/.nvm/versions/node/v24.22.1/bin/node',str(root/'run.mjs'),phase]);last=0;lastmetrics={}
while p.poll() is None:
 t=time.time()
 if t-last>=1:lastmetrics=metrics();last=t
 samples.append({'at':int(t*1000),'gpu_busy_pct':integer('/sys/class/drm/card0/device/gpu_busy_percent'),'vram_bytes':integer('/sys/class/drm/card0/device/mem_info_vram_used'),'metrics':lastmetrics});time.sleep(.25)
after=metrics();(root/(phase+'-telemetry.json')).write_text(json.dumps({'before':before,'after':after,'samples':samples,'exit_code':p.returncode}));raise SystemExit(p.returncode)
