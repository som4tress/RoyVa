import pathlib,json,urllib.request,base64
h=pathlib.Path.home();pw=(h/'llm-server/opencode.env').read_text().strip().split('=',1)[1];headers={'Authorization':'Basic '+base64.b64encode(('opencode:'+pw).encode()).decode()}
u='http://127.0.0.1:49374/api/session/ses_tg_6064019420_mvx2wk1y_ha/message'
try:
 d=json.load(urllib.request.urlopen(urllib.request.Request(u,headers=headers),timeout=10))
 if isinstance(d,dict):d=d.get('data',[])
 if isinstance(d,list):
  for m in d[-5:]:
   print('keys',list(m));info=m.get('info',m);print({k:info.get(k) for k in ['role','modelID','providerID','time','tokens']})
   for p in m.get('parts',[]):
    print(p.get('type'),len(p.get('text','')),p.get('tool'),p.get('state',{}).get('time'))
except Exception as e:print(type(e).__name__,str(e)[:100])



