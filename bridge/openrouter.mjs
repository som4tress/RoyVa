// Real OpenRouter spend and credits left, for the reply footer. One small authenticated GET, cached for 5 minutes;
// any failure just means the line is left out.
import { readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

let cache = { at: 0, line: '' };
const usd = value => `$${Number(value).toFixed(2)}`;

export function creditsLine(credits) {
  const total = Number(credits?.total_credits), used = Number(credits?.total_usage);
  if (!Number.isFinite(total) || !Number.isFinite(used)) return '';
  return `OpenRouter: spent ${usd(used)} of ${usd(total)} · left ${usd(total - used)}`;
}

export async function openRouterLine(keyFile = process.env.OPENROUTER_API_KEY_FILE || join(homedir(), 'OpenRouter.txt'), fetchImpl = fetch) {
  if (Date.now() - cache.at < 5 * 60 * 1000) return cache.line;
  try {
    const key = readFileSync(keyFile, 'utf8').trim();
    if (!key || /\s/.test(key)) return '';
    const response = await fetchImpl('https://openrouter.ai/api/v1/credits', { headers: { authorization: `Bearer ${key}` }, signal: AbortSignal.timeout(3000) });
    if (!response.ok) return '';
    cache = { at: Date.now(), line: creditsLine((await response.json()).data) };
    return cache.line;
  } catch { return ''; }
}
