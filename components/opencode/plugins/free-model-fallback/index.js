import {cloudModel} from '../../lib/routing-policy.mjs';
import {recordFreeQuota,isFreeCoolingDown} from '../../lib/free-quota.mjs';
// Free-first model fallback.
// Default model is OpenCode's free GLM-5.3-Flash. When its free budget runs out
// (or the request fails for any provider-side reason), switch the session to
// the configured cloud model on OpenRouter and retry the same turn — once.
//
// Guards: only fires for providerID "opencode"; a per-session flag stops loops;
// local evo-agent / evo-vision traffic is never touched.
const FREE = 'opencode';

export default {
 id: 'free-model-fallback',
 async setup(ctx) {
  const tried = new Set();
  await ctx.session.hook('retry', async event => {
   if (event.model?.providerID !== FREE) return;
   recordFreeQuota(event.error||event.reason||{});
   if (tried.has(event.sessionID)) { event.decision = { retry: false }; return; }
   tried.add(event.sessionID);
   try {
    await ctx.session.switchModel({ sessionID: event.sessionID, model: cloudModel() });
   } catch {
    event.decision = { retry: false };
    return;
   }
   event.decision = { retry: true, delay: 0 };
  });
  // A fresh user turn may try the free model again.
  await ctx.session.hook('prompt', async event => {
   tried.delete(event.sessionID);
   if(isFreeCoolingDown()&&ctx.session.get){const session=await ctx.session.get({sessionID:event.sessionID});if(session.model?.providerID===FREE)await ctx.session.switchModel({sessionID:event.sessionID,model:cloudModel()});}
  });
 }
};
