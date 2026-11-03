from pathlib import Path
p=Path.home()/'.config/opencode/plugins/ha-mcp-routing/index.js';s=p.read_text()
s=s.replace("    instruction+='\\nExisting naming configuration", "    instruction+='\\nCurrent local date and time from the system clock: '+new Date().toLocaleString('en-US',{timeZone:'America/Los_Angeles'})+' America/Los_Angeles. Never infer today from training data. Omit the history date argument for today.\\n';\n    instruction+='\\nExisting naming configuration")
s=s.replace("   if(!isLocal(state))return;\n   if(!allow(event.tool,state.kind))", """   if(!isLocal(state))return;
   if(event.tool==='ha-history_get_visited_locations'){
    const text=state.requestText||'';
    const explicit=/\\b\\d{4}-\\d{2}-\\d{2}\\b|\\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\\b/i.test(text);
    if(!explicit&&/\\btoday\\b/i.test(text)&&!/\\byesterday\\b/i.test(text)){event.input={...event.input};delete event.input.date;}
    else if(!explicit&&/\\byesterday\\b/i.test(text)&&!/\\btoday\\b/i.test(text)){
     const parts=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date()).filter(p=>p.type!=='literal').map(p=>[p.type,p.value]));
     const yesterday=new Date(Date.UTC(Number(parts.year),Number(parts.month)-1,Number(parts.day)-1)).toISOString().slice(0,10);
     event.input={...event.input,date:yesterday};
    }
   }
   if(!allow(event.tool,state.kind))""")
p.write_text(s)
