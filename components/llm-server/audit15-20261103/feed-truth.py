import urllib.request,xml.etree.ElementTree as E,json,datetime,concurrent.futures
feeds=['https://feeds.bbci.co.uk/news/technology/rss.xml','https://www.theverge.com/rss/index.xml','https://github.com/home-assistant/core/releases.atom','https://github.com/vllm-project/vllm/releases.atom','https://github.com/ggml-org/llama.cpp/releases.atom']
def one(url):
 try:
  raw=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'ReadOnlyAudit/1.0'}),timeout=20).read();root=E.fromstring(raw);items=[]
  for node in root.iter():
   if node.tag.split('}')[-1] not in ['item','entry']:continue
   row={}
   for ch in node:
    k=ch.tag.split('}')[-1]
    if k in ['title','pubDate','published','updated','id']:row[k]=''.join(ch.itertext())
    if k=='link':row['link']=ch.get('href') or ch.text
   items.append(row)
  return {'url':url,'retrievedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'entries':items[:8]}
 except Exception as e:return {'url':url,'error':type(e).__name__+': '+str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:results=list(pool.map(one,feeds))
open('/home/somdutta/llm-server/audit15-20261103/feed-truth.json','w').write(json.dumps(results,indent=2));print(json.dumps([{'url':r['url'],'entries':len(r.get('entries',[])),'error':r.get('error')} for r in results]))
