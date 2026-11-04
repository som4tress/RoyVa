"""Download pinned Q8 GGUF in verified ranges; validate its full SHA-256."""
import urllib.request,concurrent.futures,os,time,pathlib,json
repo='unsloth/Qwen3.6-35B-A3B-GGUF';rev='a483e9e6cbd595906af30beda3187c2663a1118c';name='Qwen3.6-35B-A3B-Q8_0.gguf'
u=f'https://huggingface.co/{repo}/resolve/{rev}/{name}'
p=pathlib.Path('/home/somdutta/llamacpp-download-20261103');p.mkdir(exist_ok=True)
meta=json.load(urllib.request.urlopen(f'https://huggingface.co/api/models/{repo}/revision/{rev}?blobs=true'))
s=next(s for s in meta['siblings'] if s['rfilename']==name);(p/'qwen36-q8-source.json').write_text(json.dumps({'repo':repo,'revision':rev,'file':s},indent=2))
req=urllib.request.Request(u,headers={'Range':'bytes=0-0'})
with urllib.request.urlopen(req,timeout=30) as r:u=r.url
size=s['size'];part=p/(name+'.part');start=0;fd=os.open(part,os.O_RDWR|os.O_CREAT,0o600);os.ftruncate(fd,size)
step=8*1024*1024;done=start;tick=time.monotonic()
def get(rng):
 a,b=rng
 for attempt in range(5):
  try:
   req=urllib.request.Request(u,headers={'Range':f'bytes={a}-{b}'})
   with urllib.request.urlopen(req,timeout=90) as r:
    if r.status!=206:raise RuntimeError(f'Expected partial response, got {r.status}')
    if r.headers.get('Content-Range')!=f'bytes {a}-{b}/{size}':raise RuntimeError('wrong content range')
    pos=a
    while data:=r.read(1024*1024):
     if pos+len(data)>b+1:raise RuntimeError('range overflow')
     os.pwrite(fd,data,pos);pos+=len(data)
    if pos!=b+1:raise RuntimeError('short range')
   return b-a+1
  except Exception:
   if attempt==4:raise
 return 0
with concurrent.futures.ThreadPoolExecutor(max_workers=64) as pool:
 for task in concurrent.futures.as_completed([pool.submit(get,(a,min(a+step-1,size-1))) for a in range(start,size,step)]):
  n=task.result()
  done+=n
  if time.monotonic()-tick>20:print(round(done/1e9,2),'/',round(size/1e9,2),'GB',flush=True);tick=time.monotonic()
os.close(fd)
import hashlib
h=hashlib.sha256()
with part.open('rb') as f:
 while b:=f.read(16*1024*1024):h.update(b)
assert h.hexdigest()==s['lfs']['sha256'],(h.hexdigest(),s['lfs'])
part.rename(p/name);print('Verified SHA256',h.hexdigest(),flush=True)
