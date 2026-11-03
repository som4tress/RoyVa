from pathlib import Path
h=Path.home();p=h/'.config/opencode/lib/execution-templates.mjs';s=p.read_text().replace("'instructions/ha-compact.md'];", "'instructions/ha-compact.md','lib/execution-templates.mjs','lib/ha-reports.mjs'];");p.write_text(s)
p=h/'.config/opencode/plugins/ha-mcp-routing/index.js';s=p.read_text().replace("   event.headers['x-request-kind']='ha';", "   event.headers['x-request-kind']='ha';\n   event.headers['x-ha-request-kind']=event.kind||'primary';\n   event.headers['x-ha-request-task']=encodeURIComponent(state.requestText||'');")
p.write_text(s)
p=h/'.config/opencode/lib/media-deadline-proxy.mjs';s=p.read_text().replace("  if(ha&&!cloud){\n   let direct=null;", """  if(ha&&!cloud&&/title/i.test(req.headers['x-ha-request-kind']||'')){
   let task='Home Assistant';try{task=decodeURIComponent(req.headers['x-ha-request-task']||task)}catch{}
   const text=task.trim().split(/\\s+/).slice(0,10).join(' ').slice(0,100)||'Home Assistant';
   const wire=reportWire(incoming,text);res.writeHead(200,{'content-type':wire.type});res.end(wire.body);
   console.log(JSON.stringify({at:new Date().toISOString(),route:'ha-title-renderer',status:200,zeroLLM:true}));return;
  }
  if(ha&&!cloud){
   let direct=null;""")
p.write_text(s)
