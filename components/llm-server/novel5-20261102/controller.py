from pathlib import Path
import os,json,subprocess,datetime,signal,urllib.request,base64
r=Path(__file__).parent;cfg=Path.home()/'.config/opencode/cloud-context.json';node=str(Path.home()/'.nvm/versions/node/v24.22.1/bin/node');active=None

def stamp(status,**extra):
 (r/'status.json').write_text(json.dumps({'status':status,'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),**extra},indent=2))
def configure():
 d=json.loads(cfg.read_text());d['enabled']=False;d['pilotStateFile']=str(r/'pilot.json');cfg.write_text(json.dumps(d,indent=2))
def cleanup():
 d=json.loads(cfg.read_text());d['enabled']=False;d.pop('pilotStateFile',None);cfg.write_text(json.dumps(d,indent=2))
def stop(signum,frame):
 global active
 for phase in ['baseline','optimized']:
  p=r/(phase+'-state.json')
  if not p.exists():continue
  service=json.loads((Path.home()/'.config/opencode/service.json').read_text())
  for sid in json.loads(p.read_text()).get('sessions',{}).values():
   try:
    req=urllib.request.Request('http://127.0.0.1:'+str(service['port'])+'/api/session/'+sid+'/interrupt',data=b'{}',headers={'Content-Type':'application/json','Authorization':'Basic '+base64.b64encode(('opencode:'+service['password']).encode()).decode()});urllib.request.urlopen(req,timeout=5).close()
   except Exception:pass
 if active:active.terminate()
 cleanup();stamp('stopped');raise SystemExit(1)
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGALRM,stop);signal.alarm(3600)
try:
 stamp('running');configure()
 for phase,workdir,enable in [('baseline','novel-a','0'),('optimized','novel-b','1')]:
  stamp('running',phase=phase);env=dict(os.environ,OPENCODE_BENCHMARK_ROOT=str(r),OPENCODE_TG_DIR=str(r/workdir),OPENCODE_BENCHMARK_OPTIMIZE=enable)
  active=subprocess.Popen([node,str(r/'run.mjs'),phase,'1,2,3,4,5'],env=env);code=active.wait();active=None
  if code:raise RuntimeError('benchmark process failed: '+phase)
 subprocess.run(['python3',str(r/'payload-report.py')],check=True);subprocess.run(['python3',str(r/'report.py')],check=True);stamp('complete',report=str(r/'REPORT.md'))
except Exception as e:stamp('failed',reason=type(e).__name__);raise
finally:cleanup()
