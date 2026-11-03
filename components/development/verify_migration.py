import urllib.request,base64,pathlib,json
h=pathlib.Path.home();pw=(h/'llm-server/opencode.env').read_text().strip().split('=',1)[1]
for route in ['/api/info','/api/session']:
 try:
  r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:49374'+route,headers={'Authorization':'Basic '+base64.b64encode(('opencode:'+pw).encode()).decode()}),timeout=8); print(route,r.status,len(r.read()))
 except Exception as e: print(route,type(e).__name__,str(e)[:150])
