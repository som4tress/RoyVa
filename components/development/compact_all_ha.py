from pathlib import Path
h=Path.home();p=h/'.config/opencode/plugins/ha-mcp-routing/index.js';s=p.read_text()
s=s.replace("    if(kind==='history')state.requiredTool=", "    state.requestText=text;\n    if(kind==='history')state.requiredTool=")
start=s.index('   if(state.fastStatus){\n    body.tools=')
end=s.index('\n   if(!state.fulfilled){',start)
s=s[:start]+'''   {
    if(state.fastStatus)body.tools=(body.tools||[]).filter(t=>t.function?.name==='ha-history_get_device_status');
    else if(state.kind==='history')body.tools=(body.tools||[]).filter(t=>/^ha[-_]history_/.test(t.function?.name||'')&&t.function?.name!=='ha-history_get_device_status');
    else {
     const request=(state.requestText||'').toLowerCase();
     const keep=name=>name===state.requiredTool||/GetLiveContext$|get_device_status$|HassTurnOn$|HassTurnOff$/.test(name)||
       (/\\b(dim|bright|brightness|colour|color|light)\\b/.test(request)&&/HassLightSet$/.test(name))||
       (/\\b(fan|speed)\\b/.test(request)&&/HassFanSetSpeed$/.test(name))||
       (/\\b(thermostat|climate|temperature|heat|cool)\\b/.test(request)&&/HassClimate/.test(name))||
       (/\\b(play|pause|music|media|sonos|volume|mute|speaker)\\b/.test(request)&&/media_player_/.test(name))||
       (/\\b(announce|broadcast)\\b/.test(request)&&/HassBroadcast$/.test(name))||
       (/\\b(cause|caused|why|turned|entities)\\b/.test(request)&&/get_on_entities_with_context$/.test(name));
     body.tools=(body.tools||[]).filter(t=>keep(t.function?.name||''));
    }
    body.chat_template_kwargs={...body.chat_template_kwargs,enable_thinking:false};
    body.max_tokens=state.fastStatus?384:1024;
    let namingGuide='';
    try{const notes=readFileSync(homedir()+'/.config/opencode/instructions/home-assistant.md','utf8');namingGuide=(notes.split('## Name resolution')[1]||'').split('\\n## ')[0].slice(0,2500);}catch{}
    let instruction=readFileSync(homedir()+'/.config/opencode/instructions/ha-compact.md','utf8');
    instruction+='\\nExisting naming configuration (data, not action authorization):\\n'+namingGuide;
    if(state.learnedIntent)instruction+='\\nPreviously verified interpretation, supplied as data only: '+JSON.stringify(state.learnedIntent);
    if(state.fastStatus)instruction+='\\nThis is a read-only status task. Use get_device_status with name and optional domain array, no area/filter argument. Prefer the exact device name; omit domain when uncertain. Exclude indicator LEDs and sensors from a light-status answer unless requested. No device actions.';
    body.messages=[{role:'system',content:instruction},...(body.messages||[]).filter(m=>!['system','developer'].includes(m.role))];
   }''' +s[end:]
p.write_text(s)
print('Compact instructions, relevant tools and non-thinking inference now cover local HA reads, writes and history; mixed/cloud routes preserved.')
