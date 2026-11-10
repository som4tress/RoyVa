// Recompute config/pricing.json from OpenRouter's public endpoint list (median across providers).
// Usage: node scripts/refresh-pricing.mjs [model-id]   (default deepseek/deepseek-v4.1-flash-1017)
import { writeFileSync } from 'node:fs';
const id = process.argv[2] || 'deepseek/deepseek-v4.1-flash-1017';
const data = (await (await fetch(`https://openrouter.ai/api/v1/models/${id}/endpoints`)).json()).data;
const median = key => {
  const v = data.endpoints.map(e => Number(e.pricing?.[key])).filter(Number.isFinite).sort((a, b) => a - b);
  const m = v.length >> 1;
  return (v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2) * 1e6;
};
const out = {
  model: data.name?.replace(/^DeepSeek:\s*/, '') || id,
  source: `OpenRouter provider-endpoint median, ${id}`,
  as_of: new Date().toISOString().slice(0, 10),
  usd_per_million: { input: +median('prompt').toFixed(5), cached_input: +median('input_cache_read').toFixed(5), output: +median('completion').toFixed(5) },
};
writeFileSync(new URL('../config/pricing.json', import.meta.url), JSON.stringify(out, null, 2) + '\n');
console.log(out);
