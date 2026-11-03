from pathlib import Path
p=Path.home()/'.config/opencode/plugins/ha-mcp-routing/index.js';s=p.read_text()
old="      if(catalog.some(tool=>allow(tool.id,kind)) && (!learned || catalog.some(tool=>tool.id===learned.route.requiredTool))){ready=true;break;}"
new="""      const statusOnly=kind==='devices'&&!/\\b(all|every|everything|turn|toggle|set|dim|change|enable|disable|why|cause|history|when|automation|script|also)\\b/i.test(text)&&/\\b(status|state|is|are)\\b/i.test(text)&&/\\b(light|lights|fan|fans|switch|switches)\\b/i.test(text);
      const requiredReady=kind==='devices'&&!statusOnly?catalog.some(tool=>/^home[-_]assistant_/.test(tool.id)):catalog.some(tool=>allow(tool.id,kind));
      if(requiredReady && (!learned || catalog.some(tool=>tool.id===learned.route.requiredTool))){ready=true;break;}
      if(attempt===0&&ctx.tool.reload)await ctx.tool.reload();"""
assert old in s;s=s.replace(old,new);p.write_text(s)
