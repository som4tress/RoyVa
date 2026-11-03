import pathlib,json,urllib.request,base64
h=pathlib.Path.home();pw=(h/'llm-server/opencode.env').read_text().strip().split('=',1)[1];headers={'Authorization':'Basic '+base64.b64encode(('opencode:'+pw).encode()).decode()}
for route in ['/api/config','/api/experimental/config']:
 try:
  d=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:49374'+route,headers=headers),timeout=8))
  def walk(x,path=''):
   if isinstance(x,dict):
    for k,v in x.items():
     if k in ['codemode','mcp','servers','home-assistant']: print(route,path+'/'+k, v if k=='codemode' else list(v) if isinstance(v,dict) else type(v).__name__)
     walk(v,path+'/'+k)
   if isinstance(x,list):
    for v in x:walk(v,path)
  walk(d)
 except Exception as e:print(type(e).__name__)
