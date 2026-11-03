from pathlib import Path
h=Path.home();base=h/'.config/opencode';backup=h/'opencode-migration-backup/history-shortcut-fix'
p=base/'telegram/bridge.mjs';(backup/'bridge-before-quota.mjs').write_text(p.read_text());s=p.read_text();s="import {quotaInfo,recordFreeQuota,isFreeCoolingDown,freeQuotaState,PAID_MODEL} from '../lib/free-quota.mjs';\n"+s
s=s.replace('    const args = ["run",', "    const requestedModel=options.model||getModel();\n    const selectedModel=requestedModel.startsWith('opencode/')&&isFreeCoolingDown()?PAID_MODEL:requestedModel;\n    let freeLimitError=null,toolActivity=false;\n    const args = [\"run\",")
s=s.replace('options.model || getModel(), "-s"','selectedModel, "-s"')
s=s.replace('        const part = ev.part;', "        const part = ev.part;\n        if(ev.type?.startsWith('tool')||part?.type==='tool')toolActivity=true;")
s=s.replace('        } else if (ev.type === "error") {', "        } else if (ev.type === \"error\") {\n          if(selectedModel.startsWith('opencode/')&&quotaInfo(ev.error)){freeLimitError=ev.error;recordFreeQuota(ev.error);}")
s=s.replace('      if (errorText) return resolve({ ok: false, text:', "      if(freeLimitError&&!options._freeFallback&&!aborted){\n        if(!toolActivity)return resolve(await runOpenCode(sessionId,prompt,{...options,model:PAID_MODEL,_freeFallback:true}));\n        return resolve({ok:false,text:'The free model reached its limit after starting this task. I have not replayed its tool calls. Ask me to continue with DeepSeek.'});\n      }\n      if (errorText) return resolve({ ok: false, text:")
s=s.replace('`default model: ${getModel()}`,', "`default model: ${getModel()}`,\n        ...(isFreeCoolingDown()?[`free quota: unavailable until ${new Date(freeQuotaState().until).toLocaleString('en-US',{timeZone:'America/Los_Angeles'})} PT; general fallback: DeepSeek`]:[]),")
p.write_text(s)
p=base/'plugins/free-model-fallback/index.js';(backup/'free-fallback-before-quota.js').write_text(p.read_text());s=p.read_text();s="import {recordFreeQuota,isFreeCoolingDown} from '../../lib/free-quota.mjs';\n"+s
s=s.replace("   if (event.model?.providerID !== FREE) return;", "   if (event.model?.providerID !== FREE) return;\n   recordFreeQuota(event.error||event.reason||{});")
s=s.replace("  await ctx.session.hook('prompt', async event => { tried.delete(event.sessionID); });", "  await ctx.session.hook('prompt', async event => {\n   tried.delete(event.sessionID);\n   if(isFreeCoolingDown()&&ctx.session.get){const session=await ctx.session.get({sessionID:event.sessionID});if(session.model?.providerID===FREE)await ctx.session.switchModel({sessionID:event.sessionID,model:PAID});}\n  });")
p.write_text(s)
print('Terminal free-quota recovery added: retry once on DeepSeek only before tool activity; persist provider cooldown. HA routing remains local-first.')
