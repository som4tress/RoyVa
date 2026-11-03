import assert from 'node:assert/strict';
import plugin from '/home/somdutta/.config/opencode/plugins/ha-mcp-routing/index.js';
const hooks={},models=[];const general={providerID:'opencode',id:'glm-5.3-flash-free'};
await plugin.setup({options:{phraseStore:'/tmp/review-phrase-none.json',learningStore:'/tmp/review-routes-none.json'},session:{hook:async(n,f)=>hooks[n]=f,get:async()=>({model:general}),switchModel:async({model})=>models.push(model)},permission:{hook:async()=>{}}});
await hooks.prompt({sessionID:'review-ha-fallback',prompt:{text:'Is the den light on?'}});
assert.equal(models[0].providerID,'evo-agent');
const event={sessionID:'review-ha-fallback',model:{providerID:'evo-agent',id:'qwen36-agent'}};await hooks.retry(event);
assert.equal(models.at(-1).providerID,'openrouter');assert.equal(models.at(-1).id,'deepseek/deepseek-v4.1-flash-1017');assert.equal(models.filter(m=>m.providerID==='opencode').length,0);
console.log('PASS: HA uses local Qwen and falls directly to DeepSeek, without GLM.');
