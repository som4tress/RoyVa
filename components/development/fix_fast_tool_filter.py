from pathlib import Path
p=Path.home()/'.config/opencode/plugins/ha-mcp-routing/index.js';s=p.read_text()
s='\n'.join(l for l in s.split('\n') if not ("event:'fast-" in l or "if(state.fastStatus)for" in l))
s=s.replace("    body.chat_template_kwargs={...body.chat_template_kwargs,enable_thinking:false};", "    body.tools=(body.tools||[]).filter(t=>t.function?.name==='home-assistant_homeassistant__GetLiveContext');\n    body.chat_template_kwargs={...body.chat_template_kwargs,enable_thinking:false};")
s=s.replace('For that room query name Shivi and domain [light];','For Shivangsh room light query name Shivi Bedroom Light with domain [switch]; it is a physical light exposed as a switch. For the study tubelight use its exact name; for room-wide lighting use name Shivi with domain [light,switch] and exclude the fan and Linux Box from light results;')
s=s.replace("    body.tool_choice=state.requiredTool?", "    body.tool_choice=state.fastStatus?{type:'function',function:{name:'home-assistant_homeassistant__GetLiveContext'}}:state.requiredTool?")
p.write_text(s)
