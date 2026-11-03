from pathlib import Path
p=Path.home()/'.config/opencode/plugins/ha-mcp-routing/index.js';s=p.read_text()
start=s.index('const history=s=>');end=s.index('\nconst devices=',start)
s=s[:start]+"const history=s=>/\\b(visit\\w*|locations?|where)\\b/.test(s)&&/\\b(today|yesterday|visited|history|locations|been|went)\\b/.test(s)&&!/\\b(stock|news|flight|ticket|vacation|holiday)\\b/.test(s);"+s[end:]
s=s.replace("   if(event.kind!=='primary'||event.model.providerID!=='evo-agent')return;\n   const state=await stateFor(event.sessionID);if(!isLocal(state))return;\n   const body=await event.request.clone().json();", """   if(event.model.providerID!=='evo-agent')return;
   const state=await stateFor(event.sessionID);if(!isLocal(state))return;
   const body=await event.request.clone().json();
   if(event.kind!=='primary'){
    body.chat_template_kwargs={...body.chat_template_kwargs,enable_thinking:false};
    body.max_tokens=Math.min(body.max_tokens||1024,/title/i.test(event.kind)?128:1024);
    event.request=new Request(event.request,{body:JSON.stringify(body)});return;
   }""")
s=s.replace("    body.tool_choice=state.fastStatus?'required':state.requiredTool?{type:'function',function:{name:state.requiredTool}}:'required';", "    if(state.requiredTool&&body.tools.some(t=>t.function?.name===state.requiredTool))body.tools=body.tools.filter(t=>t.function?.name===state.requiredTool);\n    body.tool_choice='required';")
p.write_text(s)
print('Generic history routing and HA auxiliary-token bounds installed; tool selection uses normal argument generation.')
