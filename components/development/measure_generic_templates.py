from pathlib import Path
h=Path.home();p=h/'.config/opencode/lib/media-deadline-proxy.mjs';s=p.read_text().replace("const server=http.createServer", "const metrics={upstream:0,cloud:0,local:0,templateHits:0,formattedResults:0,titles:0};\nconst server=http.createServer")
s=s.replace(" if(req.url==='/health'){res.end('ok');return;}", " if(req.url==='/health'){res.end('ok');return;}\n if(req.url==='/metrics'&&req.method==='GET'){res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify(metrics));return;}")
s=s.replace("   const wire=reportWire(incoming,text);res.writeHead", "   metrics.titles++;\n   const wire=reportWire(incoming,text);res.writeHead")
s=s.replace("   if(direct){\n    const wire=", "   if(direct){\n    if(direct.zeroLLM)metrics.templateHits++;else metrics.formattedResults++;\n    const wire=")
s=s.replace("  const upstream=await fetch", "  metrics.upstream++;if(cloud)metrics.cloud++;else metrics.local++;\n  const upstream=await fetch")
p.write_text(s)
p=h/'.config/opencode/lib/execution-templates.mjs';s=p.read_text().replace('appendFileSync,existsSync','appendFileSync,existsSync,statSync')
s=s.replace("export function fingerprint(){try{return sha(", "const codeRead=p=>{if(statSync(p).size>4*1024*1024)throw new Error('Adapter dependency too large');return readFileSync(p)};\nexport function fingerprint(){try{return sha(")
s=s.replace('FILES.map(p=>readFileSync(ROOT+\'/\'+p))',"FILES.map(p=>codeRead(ROOT+'/'+p))").replace('[...EXTRA_FILES].map(p=>readFileSync(p))','[...EXTRA_FILES].map(p=>codeRead(p))')
anchor='function readStore(path)'
insert="""function validRecipe(recipe){
 if(!recipe||!SUPPORTED.has(recipe.tool)||!['read','write'].includes(recipe.kind))return false;
 const adapter=EXTENSIONS.get(recipe.tool);
 if(adapter)return recipe.adapter===adapter.id&&((adapter.writeTools||[]).includes(recipe.tool)===(recipe.kind==='write'));
 return /HassTurn(?:On|Off)$/.test(recipe.tool)===(recipe.kind==='write');
}
"""
s=s.replace(anchor,insert+anchor)
s=s.replace("if(!code||!SUPPORTED.has(recipe?.tool)||!['read','write'].includes(recipe.kind))return false;", "if(!code||!validRecipe(recipe))return false;")
s=s.replace('&&SUPPORTED.has(t.recipe?.tool)&&now-', '&&validRecipe(t.recipe)&&now-')
p.write_text(s)
