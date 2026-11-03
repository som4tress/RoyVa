from pathlib import Path
h=Path.home();base=h/'.config/opencode';p=base/'plugins/ha-mcp-routing/index.js';s=p.read_text();s="import {isFreeCoolingDown} from '../../lib/free-quota.mjs';\n"+s
s=s.replace("    turns.delete(event.sessionID);await ctx.storage?.remove(key(event.sessionID));\n    if(prior?.previous)await ctx.session.switchModel({sessionID:event.sessionID,model:prior.previous});\n    return;", "    await save(event.sessionID,{kind:'explanation',requestText:text,previous:prior?.previous});\n    if(prior?.previous){const restored=prior.previous.providerID==='opencode'&&isFreeCoolingDown()?CLOUD:prior.previous;await ctx.session.switchModel({sessionID:event.sessionID,model:restored});}\n    return;")
s=s.replace("   if(!state)return;\n   if(['orchestrate'", "   if(!state||state.kind==='explanation')return;\n   if(['orchestrate'")
s=s.replace('if(text&&phraseKind&&rememberPhrase(', 'if(text&&phraseKind&&!isLocationExplanation(text)&&rememberPhrase(')
p.write_text(s)
p=base/'agents/telegram.md';p.write_text(p.read_text()+'\nQuestions explaining a prior incorrect answer, routing, or why history was confused with current location are meta questions. Answer the explanation directly; do not treat them as a request for a fresh person location and do not delegate them as a device/history action.\n')
p=base/'telegram/bridge.mjs';s=p.read_text();s=s.replace("  return state.sessions[key];", "  return state.sessions[key];") # Preserve existing session ownership/offset behavior.
p.write_text(s)
